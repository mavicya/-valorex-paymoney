"""
Tasks handler.

ПРАВИЛО НАРАХУВАННЯ:
  Баланс юзера НЕ змінюється тут ніколи.
  Підтвердження зберігається зі статусом "pending".
  Баланс нараховується ТІЛЬКИ в admin.py::cb_approve після ручного схвалення адміном.
"""
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import TaskFlow
from database.models import Task, TaskSubmission, User

router = Router()


# ─────────────────────────────────────────────
# СПИСОК ЗАВДАНЬ
# ─────────────────────────────────────────────
@router.message(F.text == "📋 Завдання")
async def show_tasks(message: Message, user: User, session: AsyncSession) -> None:
    result = await session.execute(
        select(Task).where(Task.is_active == True, Task.is_vip_only == False)
    )
    tasks = result.scalars().all()

    if not tasks:
        await message.answer(
            "📋 <b>Завдання</b>\n\n🕐 Наразі немає активних завдань. Заходьте пізніше.",
            parse_mode="HTML",
        )
        return

    await message.answer("📋 <b>Активні завдання:</b>", parse_mode="HTML")

    for task in tasks:
        existing = await session.execute(
            select(TaskSubmission).where(
                TaskSubmission.user_id == user.id,
                TaskSubmission.task_id == task.id,
            )
        )
        sub = existing.scalar_one_or_none()

        if sub:
            status_map = {
                "pending":  "⏳ На перевірці",
                "approved": "✅ Виконано",
                "rejected": "❌ Відхилено — можна повторити",
            }
            btn_text = status_map.get(sub.status, "—")
            # Дозволяємо повторну подачу тільки якщо відхилено
            if sub.status == "rejected":
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=btn_text, callback_data=f"task_take:{task.id}")]
                ])
            else:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=btn_text, callback_data="noop")]
                ])
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Взяти завдання", callback_data=f"task_take:{task.id}")]
            ])

        limit_line = f"\n👥 Ліміт виконань: {task.execution_limit}" if task.execution_limit else ""
        await message.answer(
            f"💼 <b>{task.title}</b>\n\n"
            f"{task.description}\n\n"
            f"🔗 <code>{task.referral_link}</code>\n"
            f"💰 Винагорода: <b>{task.reward} UAH</b>"
            f"{limit_line}",
            reply_markup=kb,
            parse_mode="HTML",
        )


# ─────────────────────────────────────────────
# ВЗЯТИ ЗАВДАННЯ → FSM
# ─────────────────────────────────────────────
@router.callback_query(F.data.startswith("task_take:"))
async def cb_task_take(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    task_id = int(callback.data.split(":")[1])

    if not user.username:
        await callback.answer(
            "❌ Для виконання завдань потрібен публічний @username.",
            show_alert=True,
        )
        return

    # Перевірка чи вже є активна (pending) подача
    existing = await session.execute(
        select(TaskSubmission).where(
            TaskSubmission.user_id == user.id,
            TaskSubmission.task_id == task_id,
            TaskSubmission.status == "pending",   # тільки активні блокуємо
        )
    )
    if existing.scalar_one_or_none():
        await callback.answer(
            "⏳ Ваше підтвердження вже на перевірці. Зачекайте рішення адміна.",
            show_alert=True,
        )
        return

    # Також блокуємо якщо вже approved
    approved = await session.execute(
        select(TaskSubmission).where(
            TaskSubmission.user_id == user.id,
            TaskSubmission.task_id == task_id,
            TaskSubmission.status == "approved",
        )
    )
    if approved.scalar_one_or_none():
        await callback.answer("✅ Це завдання ви вже виконали.", show_alert=True)
        return

    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task or not task.is_active:
        await callback.answer("Завдання вже неактивне.", show_alert=True)
        return

    # Перевірка ліміту виконань
    if task.execution_limit:
        count_res = await session.execute(
            select(TaskSubmission).where(
                TaskSubmission.task_id == task_id,
                TaskSubmission.status == "approved",
            )
        )
        if len(count_res.scalars().all()) >= task.execution_limit:
            await callback.answer("❌ Ліміт виконань вичерпано.", show_alert=True)
            return

    # Зберігаємо task_id І поточну суму винагороди у стані FSM
    await state.set_state(TaskFlow.waiting_proof)
    await state.update_data(
        task_id=task_id,
        task_title=task.title,
        task_reward=str(task.reward),   # snapshot суми на момент взяття
    )

    await callback.message.answer(
        f"📋 <b>{task.title}</b>\n\n"
        f"🔗 Посилання: {task.referral_link}\n\n"
        "📸 Надішліть <b>скріншот</b> або ваш <b>Username / ID</b> "
        "як підтвердження виконання:",
        parse_mode="HTML",
    )
    await callback.answer()


# ─────────────────────────────────────────────
# ОТРИМАТИ ПІДТВЕРДЖЕННЯ
# ─────────────────────────────────────────────
@router.message(TaskFlow.waiting_proof)
async def receive_proof(
    message: Message,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    task_id     = data["task_id"]
    task_reward = Decimal(data["task_reward"])   # сума зафіксована в момент взяття

    # Фінальна перевірка на дублювання — захист від race condition
    existing = await session.execute(
        select(TaskSubmission).where(
            TaskSubmission.user_id == user.id,
            TaskSubmission.task_id == task_id,
            TaskSubmission.status.in_(["pending", "approved"]),
        )
    )
    if existing.scalar_one_or_none():
        await state.clear()
        await message.answer(
            "❌ Підтвердження для цього завдання вже існує.\n"
            "Зачекайте рішення адміністратора.",
        )
        return

    proof_text    = message.text or message.caption
    proof_file_id = message.photo[-1].file_id if message.photo else None

    # БАЛАНС ТУТ НЕ ЗМІНЮЄТЬСЯ.
    # Статус = "pending". Нарахування — тільки через cb_approve в admin.py.
    sub = TaskSubmission(
        user_id=user.id,
        task_id=task_id,
        proof_text=proof_text,
        proof_file_id=proof_file_id,
        status="pending",
        reward_snapshot=task_reward,   # фіксуємо суму
    )
    session.add(sub)
    await session.flush()   # отримуємо sub.id без commit
    await session.commit()  # тільки тут зберігаємо в БД

    await state.clear()
    await _notify_admins(message, user, sub, data["task_title"], task_reward)

    await message.answer(
        "⏳ <b>Підтвердження відправлено!</b>\n\n"
        "Адміністратор перевірить виконання і ви отримаєте сповіщення.\n"
        "<i>Кошти будуть нараховані тільки після схвалення.</i>",
        parse_mode="HTML",
    )


async def _notify_admins(
    message: Message,
    user: User,
    sub: TaskSubmission,
    task_title: str,
    reward: Decimal,
) -> None:
    from config import settings

    text = (
        f"📋 <b>Нове підтвердження!</b>\n\n"
        f"👤 @{user.username or '—'} (<code>{user.id}</code>)\n"
        f"📌 Завдання: <b>{task_title}</b>\n"
        f"💰 Сума до нарахування: <code>{reward} UAH</code>\n"
        f"🆔 Submission ID: <code>{sub.id}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Прийняти", callback_data=f"sub_approve:{sub.id}"),
            InlineKeyboardButton(text="❌ Відхилити", callback_data=f"sub_reject:{sub.id}"),
        ]
    ])

    for admin_id in settings.ADMIN_IDS:
        try:
            if sub.proof_file_id:
                await message.bot.send_photo(
                    admin_id, sub.proof_file_id, caption=text,
                    reply_markup=kb, parse_mode="HTML",
                )
            else:
                await message.bot.send_message(
                    admin_id, text, reply_markup=kb, parse_mode="HTML",
                )
        except Exception:
            pass


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
