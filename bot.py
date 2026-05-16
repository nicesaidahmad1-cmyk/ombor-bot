import os
import logging
from datetime import date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from supabase import create_client

logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vgimmeafqpsakwftrszy.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_796EimvdPJs8XNZksdTFvA_DB9uSVNn")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8627653093:AAGtP5bkxT8sL0lmAZH_6N8s-2Cw05CgJg4")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
user_states = {}

def today():
    return date.today().isoformat()

def week_ago():
    return (date.today() - timedelta(days=7)).isoformat()

async def get_shop(tid):
    r = sb.table("shops").select("*").eq("telegram_id", str(tid)).maybe_single().execute()
    return r.data

async def check_active(tid):
    shop = await get_shop(tid)
    if not shop: return None, "notfound"
    if not shop.get("active"): return shop, "inactive"
    return shop, "ok"

def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Bosh sahifa"), KeyboardButton("📋 Ombor")],
        [KeyboardButton("➕ Kirim"), KeyboardButton("🛍️ Sotuv")],
        [KeyboardButton("📜 Tarix"), KeyboardButton("ℹ️ Hisob")]
    ], resize_keyboard=True)

# ── START ──────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = str(update.effective_user.id)
    shop = await get_shop(tid)
    if shop:
        if shop.get("active"):
            await update.message.reply_text(f"✅ Xush kelibsiz, *{shop['name']}*!", parse_mode="Markdown", reply_markup=main_menu())
        else:
            await update.message.reply_text("⏳ Hisobingiz hali faollashtirilmagan. Admin kutilmoqda.")
    else:
        await update.message.reply_text("👋 Salom! Botga xush kelibsiz!\n\n📝 Dukon nomingizni yozing:")
        user_states[tid] = "reg_nom"

# ── MESSAGE HANDLER ────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = str(update.effective_user.id)
    text = update.message.text.strip()
    state = user_states.get(tid)

    # Admin commands
    if text.startswith("/activate_") and update.effective_user.id == ADMIN_ID:
        target = text.replace("/activate_", "")
        sb.table("shops").update({"active": True}).eq("telegram_id", target).execute()
        shop = sb.table("shops").select("name").eq("telegram_id", target).maybe_single().execute().data
        await update.message.reply_text(f"✅ {shop['name'] if shop else target} faollashtirildi!")
        try: await ctx.bot.send_message(int(target), "🎉 Hisobingiz faollashtirildi! /start bosing.", reply_markup=main_menu())
        except: pass
        return

    if text.startswith("/deactivate_") and update.effective_user.id == ADMIN_ID:
        target = text.replace("/deactivate_", "")
        sb.table("shops").update({"active": False}).eq("telegram_id", target).execute()
        await update.message.reply_text(f"❌ O'chirildi.")
        return

    # Registration
    if state == "reg_nom":
        ex = sb.table("shops").select("id").eq("name", text).execute()
        if ex.data:
            await update.message.reply_text("⚠️ Bu nom band. Boshqa nom:")
            return
        sb.table("shops").insert({"name": text, "telegram_id": tid, "active": False}).execute()
        user_states.pop(tid, None)
        await update.message.reply_text(f"✅ *{text}* ro'yxatdan o'tdi!\n⏳ Admin faollashtirishi kutilmoqda.\n🆔 ID: `{tid}`", parse_mode="Markdown")
        if ADMIN_ID:
            try:
                await ctx.bot.send_message(ADMIN_ID, f"🆕 Yangi ro'yxat:\nDukon: *{text}*\nID: `{tid}`\nFaollashtirish: /activate_{tid}", parse_mode="Markdown")
            except: pass
        return

    shop, status = await check_active(tid)
    if status == "notfound": await start(update, ctx); return
    if status == "inactive": await update.message.reply_text("⏳ Hisobingiz faol emas."); return

    # Main menu
    if text == "📊 Bosh sahifa": await show_bosh(update, shop); return
    if text == "📋 Ombor": await show_ombor(update, shop); return
    if text == "➕ Kirim": await show_kirim(update, shop, tid); return
    if text == "🛍️ Sotuv": await show_sotuv(update, shop, tid); return
    if text == "📜 Tarix": await show_tarix(update, shop); return
    if text == "ℹ️ Hisob": await show_hisob(update, shop); return

    # State machine
    if isinstance(state, dict):
        step = state.get("step")

        # --- KIRIM: yangi model ---
        if step == "model_nom":
            user_states[tid] = {**state, "step": "model_olcham", "nom": text}
            await update.message.reply_text("📐 O'lchamini yozing (masalan: 3-4 yosh, 5-6 yosh, S/M/L):")

        elif step == "model_olcham":
            user_states[tid] = {**state, "step": "model_ranglar", "olcham": text}
            await update.message.reply_text(
                "🎨 Ranglar va pochkalarni yozing.\n\n"
                "Har bir rangni vergul bilan ajrating:\n"
                "`Qizil-5, Ko'k-3, Sariq-2, Oq-10`\n\n"
                "Yoki har bir qatorga:\n`Qizil-5`\n`Ko'k-3`",
                parse_mode="Markdown"
            )

        elif step == "model_ranglar":
            # Parse ranglar
            ranglar = []
            # Support both comma and newline separated
            items = [x.strip() for x in text.replace("\n", ",").split(",") if x.strip()]
            errors = []
            for item in items:
                if "-" in item:
                    parts = item.rsplit("-", 1)
                    rang = parts[0].strip()
                    try:
                        soni = int(parts[1].strip())
                        ranglar.append({"rang": rang, "stock": soni})
                    except:
                        errors.append(item)
                else:
                    errors.append(item)

            if not ranglar:
                await update.message.reply_text("⚠️ Format noto'g'ri! Masalan: `Qizil-5, Ko'k-3`", parse_mode="Markdown")
                return

            # Save model
            model_r = sb.table("models").insert({
                "shop_id": shop["id"],
                "nom": state["nom"],
                "olcham": state.get("olcham", "")
            }).execute()
            model_id = model_r.data[0]["id"]

            # Save ranglar
            for r in ranglar:
                sb.table("ranglar").insert({
                    "model_id": model_id,
                    "rang": r["rang"],
                    "stock": r["stock"],
                    "sotildi": 0
                }).execute()

            user_states.pop(tid, None)
            rang_text = "\n".join([f"  • {r['rang']}: {r['stock']} pochka" for r in ranglar])
            warn = f"\n⚠️ Noto'g'ri: {', '.join(errors)}" if errors else ""
            await update.message.reply_text(
                f"✅ *{state['nom']}* ({state.get('olcham','')}) qo'shildi!\n\n{rang_text}{warn}",
                parse_mode="Markdown", reply_markup=main_menu()
            )

        # --- KIRIM: mavjudga qo'shish ---
        elif step == "add_stock":
            try:
                soni = int(text)
                r = state["rang"]
                sb.table("ranglar").update({"stock": r["stock"] + soni}).eq("id", r["id"]).execute()
                user_states.pop(tid, None)
                await update.message.reply_text(
                    f"✅ *{state['model_nom']}* — {r['rang']} ga {soni} pochka qo'shildi!\nJami: {r['stock']+soni} pochka",
                    parse_mode="Markdown", reply_markup=main_menu()
                )
            except: await update.message.reply_text("⚠️ Son kiriting!")

        # --- SOTUV ---
        elif step == "sotuv_soni":
            try:
                soni = int(text)
                r = state["rang"]
                model_nom = state["model_nom"]
                if r["stock"] < soni:
                    await update.message.reply_text(f"⚠️ Faqat {r['stock']} pochka bor!")
                    return
                sana = state.get("sana", today())
                sb.table("sales").insert({"shop_id": shop["id"], "rang_id": r["id"], "soni": soni, "sana": sana}).execute()
                sb.table("ranglar").update({"stock": r["stock"]-soni, "sotildi": r["sotildi"]+soni}).eq("id", r["id"]).execute()
                user_states.pop(tid, None)
                qoldi = r["stock"] - soni
                warn = f"\n⚠️ Faqat {qoldi} pochka qoldi!" if qoldi <= 3 else ""
                await update.message.reply_text(
                    f"✅ Saqlandi!\n*{model_nom}* — {r['rang']}: {soni} pochka{warn}",
                    parse_mode="Markdown", reply_markup=main_menu()
                )
            except: await update.message.reply_text("⚠️ Son kiriting!")

        # --- SOTUV: daftar sanasi ---
        elif step == "sotuv_sana":
            try:
                # Accept DD.MM.YYYY or YYYY-MM-DD
                if "." in text:
                    parts = text.split(".")
                    sana = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                else:
                    sana = text
                date.fromisoformat(sana)
                user_states[tid] = {**state, "step": "sotuv_soni", "sana": sana}
                r = state["rang"]
                await update.message.reply_text(f"📦 {state['model_nom']} — {r['rang']}\nNechta pochka? ({sana} sanasi uchun)")
            except:
                await update.message.reply_text("⚠️ Sana noto'g'ri! Masalan: 12.05.2026")
    else:
        await update.message.reply_text("Quyidagilardan birini tanlang:", reply_markup=main_menu())

# ── SHOW FUNCTIONS ─────────────────────────────────────
async def show_bosh(update, shop):
    models = sb.table("models").select("*, ranglar(*)").eq("shop_id", shop["id"]).execute().data or []
    sales = sb.table("sales").select("soni,sana").eq("shop_id", shop["id"]).gte("sana", week_ago()).execute().data or []

    jami_pk = sum(r["stock"] for m in models for r in m.get("ranglar", []))
    bugun = sum(s["soni"] for s in sales if s["sana"] == today())
    hafta = sum(s["soni"] for s in sales)

    # Top 3 model by sotildi
    model_stats = []
    for m in models:
        total_sotildi = sum(r["sotildi"] for r in m.get("ranglar", []))
        model_stats.append((m["nom"], m.get("olcham",""), total_sotildi))
    top = sorted(model_stats, key=lambda x: x[2], reverse=True)[:3]
    top_text = "\n".join([f"  {i+1}. {n} ({o}) — {s}pk" for i,(n,o,s) in enumerate(top)]) or "  Hali sotuv yo'q"

    # Kam qolgan ranglar
    kam = []
    for m in models:
        for r in m.get("ranglar", []):
            if r["stock"] <= 3:
                kam.append(f"  ⚠️ {m['nom']} — {r['rang']}: {r['stock']}pk")
    kam_text = "\n".join(kam[:8]) or "  Hammasi yetarli ✅"

    await update.message.reply_text(
        f"📊 *{shop['name']}*\n\n"
        f"📦 Jami pochka: *{jami_pk}*\n"
        f"🛍️ Bugun: *{bugun}pk*  |  Hafta: *{hafta}pk*\n"
        f"🗂️ Model soni: *{len(models)}*\n\n"
        f"🏆 *Top modellar:*\n{top_text}\n\n"
        f"⚠️ *Kam qolgan:*\n{kam_text}",
        parse_mode="Markdown"
    )

async def show_ombor(update, shop):
    models = sb.table("models").select("*, ranglar(*)").eq("shop_id", shop["id"]).order("created_at", desc=True).execute().data or []
    if not models:
        await update.message.reply_text("📋 Hali model yo'q. ➕ Kirimdan qo'shing.")
        return

    text = f"📋 *{shop['name']} — Ombor*\n\n"
    for m in models:
        ranglar = m.get("ranglar", [])
        jami = sum(r["stock"] for r in ranglar)
        text += f"👕 *{m['nom']}*"
        if m.get("olcham"): text += f" ({m['olcham']})"
        text += f" — jami {jami}pk\n"
        for r in sorted(ranglar, key=lambda x: x["stock"], reverse=True):
            icon = "🔴" if r["stock"]==0 else "🟡" if r["stock"]<=3 else "🟢"
            text += f"  {icon} {r['rang']}: *{r['stock']}pk*"
            if r["sotildi"]: text += f" (sotildi: {r['sotildi']})"
            text += "\n"
        text += "\n"
        if len(text) > 3500:
            await update.message.reply_text(text, parse_mode="Markdown")
            text = ""

    if text.strip():
        await update.message.reply_text(text, parse_mode="Markdown")

async def show_kirim(update, shop, tid):
    buttons = [
        [InlineKeyboardButton("🆕 Yangi model qo'shish", callback_data="new_model")]
    ]
    models = sb.table("models").select("id,nom,olcham,ranglar(id,rang,stock)").eq("shop_id", shop["id"]).order("created_at", desc=True).limit(20).execute().data or []
    for m in models:
        label = f"➕ {m['nom']}"
        if m.get("olcham"): label += f" ({m['olcham']})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"model_kirim_{m['id']}")])

    await update.message.reply_text("➕ *Kirim — nima qilasiz?*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def show_sotuv(update, shop, tid):
    models = sb.table("models").select("id,nom,olcham").eq("shop_id", shop["id"]).order("created_at", desc=True).limit(20).execute().data or []
    if not models:
        await update.message.reply_text("⚠️ Hali model yo'q.")
        return
    buttons = []
    for m in models:
        label = f"🛍️ {m['nom']}"
        if m.get("olcham"): label += f" ({m['olcham']})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"model_sotuv_{m['id']}")])
    await update.message.reply_text("🛍️ *Sotuv — qaysi model?*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def show_tarix(update, shop):
    sales = sb.table("sales").select("soni,sana,ranglar(rang,models(nom,olcham))").eq("shop_id", shop["id"]).order("created_at", desc=True).limit(30).execute().data or []
    if not sales:
        await update.message.reply_text("📜 Tarix yo'q.")
        return
    text = f"📜 *So'nggi 30 sotuv*\n\n"
    for s in sales:
        r = s.get("ranglar") or {}
        m = r.get("models") or {}
        nom = m.get("nom","?")
        olcham = m.get("olcham","")
        rang = r.get("rang","?")
        text += f"📅 {s['sana']} | *{nom}*"
        if olcham: text += f" ({olcham})"
        text += f" — {rang}: {s['soni']}pk\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def show_hisob(update, shop):
    await update.message.reply_text(
        f"ℹ️ *Hisob*\n\n🏪 {shop['name']}\n🆔 `{shop['telegram_id']}`\n✅ Holat: {'Faol' if shop.get('active') else 'Faol emas'}",
        parse_mode="Markdown"
    )

# ── CALLBACK HANDLER ───────────────────────────────────
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tid = str(query.from_user.id)
    data = query.data
    shop, status = await check_active(tid)
    if status != "ok":
        await query.message.reply_text("❌ Hisob faol emas.")
        return

    if data == "new_model":
        user_states[tid] = {"step": "model_nom"}
        await query.message.reply_text("📝 Yangi model nomini yozing (masalan: Ayiq futbolka, Gul ko'ylak):")

    elif data.startswith("model_kirim_"):
        model_id = data.replace("model_kirim_", "")
        model = sb.table("models").select("nom,olcham,ranglar(*)").eq("id", model_id).single().execute().data
        ranglar = model.get("ranglar", [])
        buttons = []
        for r in ranglar:
            buttons.append([InlineKeyboardButton(f"➕ {r['rang']} — {r['stock']}pk", callback_data=f"add_rang_{r['id']}")])
        buttons.append([InlineKeyboardButton("🆕 Yangi rang qo'shish", callback_data=f"new_rang_{model_id}")])
        nom = model["nom"]
        if model.get("olcham"): nom += f" ({model['olcham']})"
        await query.message.reply_text(f"➕ *{nom}*\n\nQaysi rangga kirim?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("add_rang_"):
        rang_id = data.replace("add_rang_", "")
        rang = sb.table("ranglar").select("*,models(nom)").eq("id", rang_id).single().execute().data
        model_nom = rang.get("models", {}).get("nom", "")
        user_states[tid] = {"step": "add_stock", "rang": rang, "model_nom": model_nom}
        await query.message.reply_text(f"📦 *{model_nom}* — {rang['rang']} ({rang['stock']}pk bor)\nNechta pochka qo'shildi?", parse_mode="Markdown")

    elif data.startswith("new_rang_"):
        model_id = data.replace("new_rang_", "")
        model = sb.table("models").select("nom,olcham").eq("id", model_id).single().execute().data
        user_states[tid] = {"step": "model_ranglar", "nom": model["nom"], "olcham": model.get("olcham",""), "model_id": model_id, "existing": True}
        await query.message.reply_text("🎨 Yangi ranglar yozing:\n`Qizil-5, Ko'k-3`", parse_mode="Markdown")

    elif data.startswith("model_sotuv_"):
        model_id = data.replace("model_sotuv_", "")
        model = sb.table("models").select("nom,olcham,ranglar(*)").eq("id", model_id).single().execute().data
        ranglar = [r for r in model.get("ranglar", []) if r["stock"] > 0]
        if not ranglar:
            await query.message.reply_text("⚠️ Bu modelda stock yo'q.")
            return
        buttons = [[InlineKeyboardButton(f"🔵 {r['rang']} — {r['stock']}pk", callback_data=f"sell_rang_{r['id']}")] for r in ranglar]
        nom = model["nom"]
        if model.get("olcham"): nom += f" ({model['olcham']})"
        await query.message.reply_text(f"🛍️ *{nom}*\n\nQaysi rang?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("sell_rang_"):
        rang_id = data.replace("sell_rang_", "")
        rang = sb.table("ranglar").select("*,models(nom,olcham)").eq("id", rang_id).single().execute().data
        m = rang.get("models", {})
        model_nom = m.get("nom","")
        if m.get("olcham"): model_nom += f" ({m['olcham']})"
        # Ask: today or daftar
        buttons = [
            [InlineKeyboardButton("📅 Bugun", callback_data=f"sell_today_{rang_id}")],
            [InlineKeyboardButton("📓 Daftardan (boshqa sana)", callback_data=f"sell_daftar_{rang_id}")]
        ]
        await query.message.reply_text(f"🛍️ *{model_nom}* — {rang['rang']}\n\nQachon sotildi?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("sell_today_"):
        rang_id = data.replace("sell_today_", "")
        rang = sb.table("ranglar").select("*,models(nom,olcham)").eq("id", rang_id).single().execute().data
        m = rang.get("models", {})
        model_nom = m.get("nom","")
        if m.get("olcham"): model_nom += f" ({m['olcham']})"
        user_states[tid] = {"step": "sotuv_soni", "rang": rang, "model_nom": model_nom, "sana": today()}
        await query.message.reply_text(f"📦 *{model_nom}* — {rang['rang']} ({rang['stock']}pk)\nNechta pochka?", parse_mode="Markdown")

    elif data.startswith("sell_daftar_"):
        rang_id = data.replace("sell_daftar_", "")
        rang = sb.table("ranglar").select("*,models(nom,olcham)").eq("id", rang_id).single().execute().data
        m = rang.get("models", {})
        model_nom = m.get("nom","")
        if m.get("olcham"): model_nom += f" ({m['olcham']})"
        user_states[tid] = {"step": "sotuv_sana", "rang": rang, "model_nom": model_nom}
        await query.message.reply_text(f"📅 Sanani yozing (masalan: 13.05.2026):")

# ── ADMIN ──────────────────────────────────────────────
async def admin_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    shops = sb.table("shops").select("*").execute().data or []
    if not shops: await update.message.reply_text("Hali duk on yo'q."); return
    text = "🏪 *Barcha dukonlar:*\n\n"
    for s in shops:
        icon = "✅" if s.get("active") else "⏳"
        text += f"{icon} *{s['name']}* — `{s['telegram_id']}`\n"
        text += f"   /activate_{s['telegram_id']}  |  /deactivate_{s['telegram_id']}\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", admin_list))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
