#!/usr/bin/env python3
"""
🇰🇷 Koreys-O'zbek Lug'at Quiz Bot
Rasmdan olingan so'zlar bo'yicha avtomatik test
"""

import asyncio
import json
import random
import anthropic

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ─── SOZLAMALAR ───────────────────────────────────────────────
BOT_TOKEN         = "YOUR_BOT_TOKEN"
ANTHROPIC_API_KEY = "YOUR_ANTHROPIC_KEY"
TIME_PER_Q        = 30
# ──────────────────────────────────────────────────────────────

ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── LUG'AT (rasmdan) ─────────────────────────────────────────
VOCAB = [
    ("항상",    "har doim"),
    ("한번 개",  "1 dona"),
    ("설탕",    "shakar"),
    ("지하철",   "metro"),
    ("가게",    "do'kon"),
    ("끝났어요", "tugadi"),
    ("이따금",   "ba'zan"),
    ("갑자기",   "to'satdan"),
    ("시원한",   "salqin"),
    ("바람",    "shamol"),
    ("고향",    "yurt / tug'ilgan joy"),
    ("도시",    "shahar"),
    ("나무",    "daraxt"),
    ("오늘",    "bugun"),
    ("내일",    "ertaga"),
    ("어제",    "kecha"),
    ("아침",    "tong / nonushta"),
    ("점심",    "tush / tushlik"),
    ("저녁",    "kechki ovqat"),
    ("밤",     "tun / kecha"),
]

# Barcha o'zbek so'zlar (noto'g'ri variantlar uchun)
ALL_UZ = [v for _, v in VOCAB]
ALL_KR = [k for k, _ in VOCAB]

users = {}


def get_user(uid):
    if uid not in users:
        users[uid] = {
            "active": False, "idx": 0, "score": 0,
            "answered": False, "timer": None,
            "questions": [], "mode": "kr_to_uz"
        }
    return users[uid]


# ─── /start ───────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    users[uid] = get_user(uid)
    users[uid].update({"active": False, "idx": 0, "score": 0})

    keyboard = [
        [InlineKeyboardButton("🇰🇷 Koreys → O'zbek", callback_data="mode_kr_to_uz")],
        [InlineKeyboardButton("🇺🇿 O'zbek → Koreys", callback_data="mode_uz_to_kr")],
        [InlineKeyboardButton("🔀 Aralash",           callback_data="mode_mixed")],
    ]
    await update.message.reply_text(
        "🇰🇷 *Koreys-O'zbek Lug'at Quiz!*\n\n"
        f"📚 {len(VOCAB)} ta so'z mavjud\n"
        "⏱ Har savol uchun *30 sekund*\n"
        "🏆 Yakunida bал chiqadi\n\n"
        "📌 *Test turini tanlang:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# ─── REJIM TANLASH ────────────────────────────────────────────
async def handle_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = query.from_user.id
    u    = get_user(uid)
    mode = query.data.replace("mode_", "")
    u["mode"] = mode

    mode_names = {
        "kr_to_uz": "🇰🇷 Koreys → O'zbek",
        "uz_to_kr": "🇺🇿 O'zbek → Koreys",
        "mixed":    "🔀 Aralash"
    }

    # Savollarni tayyorla
    pairs = VOCAB.copy()
    random.shuffle(pairs)
    questions = []

    for kr, uz in pairs:
        if mode == "kr_to_uz":
            question = kr
            correct  = uz
            pool     = [v for v in ALL_UZ if v != uz]
        elif mode == "uz_to_kr":
            question = uz
            correct  = kr
            pool     = [v for v in ALL_KR if v != kr]
        else:  # mixed
            if random.random() > 0.5:
                question = kr
                correct  = uz
                pool     = [v for v in ALL_UZ if v != uz]
            else:
                question = uz
                correct  = kr
                pool     = [v for v in ALL_KR if v != kr]

        wrongs  = random.sample(pool, min(3, len(pool)))
        choices = [correct] + wrongs
        random.shuffle(choices)
        questions.append({"q": question, "correct": correct, "choices": choices})

    u["questions"] = questions
    u["idx"]       = 0
    u["score"]     = 0
    u["active"]    = True

    await query.edit_message_text(
        f"✅ *{mode_names[mode]}* rejimi tanlandi!\n\n"
        f"🚀 {len(questions)} ta savol | ⏱ {TIME_PER_Q} sekund/savol\n\n"
        "Boshlayapmiz...",
        parse_mode="Markdown"
    )

    await asyncio.sleep(1)
    await send_question(query.message.chat_id, uid, ctx)


# ─── SAVOL YUBORISH ───────────────────────────────────────────
async def send_question(chat_id, uid, ctx):
    u   = get_user(uid)
    idx = u["idx"]
    qs  = u["questions"]

    if idx >= len(qs):
        await finish_test(chat_id, uid, ctx)
        return

    q        = qs[idx]
    u["answered"] = False
    letters  = ["🅐", "🅑", "🅒", "🅓"]

    keyboard = [
        [InlineKeyboardButton(
            f"{letters[i]}  {choice}",
            callback_data=f"a|{uid}|{idx}|{choice == q['correct']}"
        )]
        for i, choice in enumerate(q["choices"])
    ]

    await ctx.bot.send_message(
        chat_id=chat_id,
        text=(
            f"❓ *{idx+1}/{len(qs)}-savol*\n\n"
            f"*{q['q']}*\n\n"
            f"⏱ _{TIME_PER_Q} sekund_"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

    if u["timer"]:
        u["timer"].cancel()
    u["timer"] = asyncio.create_task(
        timeout_handler(chat_id, uid, ctx, idx)
    )


# ─── VAQT TUGADI ──────────────────────────────────────────────
async def timeout_handler(chat_id, uid, ctx, q_idx):
    await asyncio.sleep(TIME_PER_Q)
    u = get_user(uid)
    if u["idx"] == q_idx and not u["answered"] and u["active"]:
        u["answered"] = True
        u["idx"]      += 1
        correct = u["questions"][q_idx]["correct"]
        await ctx.bot.send_message(
            chat_id=chat_id,
            text=f"⏰ *Vaqt tugadi!*\n✅ To'g'ri javob: *{correct}*",
            parse_mode="Markdown"
        )
        await asyncio.sleep(1.5)
        await send_question(chat_id, uid, ctx)


# ─── JAVOB ────────────────────────────────────────────────────
async def handle_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts      = query.data.split("|")
    target_uid = int(parts[1])
    q_idx      = int(parts[2])
    is_correct = parts[3] == "True"

    uid = query.from_user.id
    if uid != target_uid:
        await query.answer("❌ Bu sizning testingiz emas!", show_alert=True)
        return

    u = get_user(uid)
    if u["answered"]:
        await query.answer("Allaqachon javob berdingiz!", show_alert=True)
        return
    if u["idx"] != q_idx:
        return

    u["answered"] = True
    if u["timer"]:
        u["timer"].cancel()

    q       = u["questions"][q_idx]
    correct = q["correct"]

    if is_correct:
        u["score"] += 1
        await query.edit_message_text(
            f"✅ *To'g'ri! +1 ball*\n\n"
            f"*{q['q']}* = *{correct}*",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            f"❌ *Noto'g'ri!*\n\n"
            f"*{q['q']}* = *{correct}*",
            parse_mode="Markdown"
        )

    u["idx"] += 1
    await asyncio.sleep(1.5)
    await send_question(query.message.chat_id, uid, ctx)


# ─── YAKUNIY NATIJA ───────────────────────────────────────────
async def finish_test(chat_id, uid, ctx):
    u     = get_user(uid)
    total = len(u["questions"])
    score = u["score"]
    pct   = round(score / total * 100) if total else 0

    if pct == 100:  grade = "🏅 Mukammal!"
    elif pct >= 80: grade = "🥇 A'lo"
    elif pct >= 60: grade = "🥈 Yaxshi"
    elif pct >= 40: grade = "🥉 Qoniqarli"
    else:           grade = "❌ Yana mashq qiling"

    u["active"] = False

    # Xato so'zlar ro'yxati
    wrong_list = ""
    for i, q in enumerate(u["questions"]):
        if i >= u["idx"]:
            break

    await ctx.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🏁 *Test yakunlandi!*\n\n"
            f"📊 Natija:  *{score}/{total}*\n"
            f"📈 Foiz:    *{pct}%*\n"
            f"🎯 Baho:    {grade}\n\n"
            f"{'🎉 Zo\'r! Barcha so\'zlarni bilasiz!' if pct == 100 else '💪 Yana bir bor urinib ko\'ring!'}\n\n"
            f"🔄 Qayta boshlash: /start"
        ),
        parse_mode="Markdown"
    )


# ─── /lugat — barcha so'zlarni ko'rish ───────────────────────
async def cmd_lugat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = "📚 *Barcha so'zlar:*\n\n"
    for i, (kr, uz) in enumerate(VOCAB, 1):
        text += f"{i}. {kr} — {uz}\n"
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── ASOSIY ───────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("lugat",  cmd_lugat))
    app.add_handler(CallbackQueryHandler(handle_mode,   pattern=r"^mode_"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^a\|"))

    print("✅ Lug'at Quiz Bot ishga tushdi!")
    app.run_polling()


if __name__ == "__main__":
    main()
