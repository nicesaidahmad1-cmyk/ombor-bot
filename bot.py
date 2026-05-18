import os
import logging
from datetime import date, timedelta
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
SB_URL = os.environ.get("SUPABASE_URL", "https://vgimmeafqpsakwftrszy.supabase.co")
SB_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_796EimvdPJs8XNZksdTFvA_DB9uSVNn")

HEADERS = {
    "apikey": SB_KEY,
    "Authorization": f"Bearer {SB_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

async def db_get(table, params=""):
    url = f"{SB_URL}/rest/v1/{table}"
    if params:
        url += f"?{params}"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url, headers=HEADERS)
        return r.json()

async def db_post(table, data):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{SB_URL}/rest/v1/{table}", headers=HEADERS, json=data)
        return r.json()

async def db_patch(table, params, data):
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.patch(f"{SB_URL}/rest/v1/{table}?{params}", headers=HEADERS, json=data)
        return r.json()

user_states = {}

def today():
    return date.today().isoformat()

def week_ago():
    return (date.today() - timedelta(days=7)).isoformat()

async def get_shop(tid):
    data = await db_get("shops", f"telegram_id=eq.{tid}&limit=1")
    if isinstance(data, list) and data:
        return data[0]
    return None

def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Bosh sahifa"), KeyboardButton("📋 Ombor")],
        [KeyboardButton("➕ Kirim"), KeyboardButton("🛍️ Sotuv")],
        [KeyboardButton("📜 Tarix"), KeyboardButton("ℹ️ Hisob")]
    ], resize_keyboard=True)

def is_admin(user_id):
    return ADMIN_ID != 0 and user_id == ADMIN_ID

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = str(update.effective_user.id)
    uid = update.effective_user.id
    
    # Admin always gets full access
    if is_admin(uid):
        await update.message.reply_text(
            f"👑 Admin paneli\n\nBuyruqlar:\n/list — barcha dukonlar\n/activate_ID — faollashtirish\n/deactivate_ID — o'chirish",
            reply_markup=main_menu()
        )
        return
    
    shop = await get_shop(tid)
    if shop:
        if shop.get("active"):
            await update.message.reply_text(
                f"✅ Xush kelibsiz, *{shop['name']}*!",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        else:
            await update.message.reply_text("⏳ Hisobingiz hali faollashtirilmagan. Admin kutilmoqda.")
    else:
        await update.message.reply_text("👋 Salom! Ombor Manager botiga xush kelibsiz!\n\n📝 Dukon nomingizni yozing:")
        user_states[tid] = "reg_nom"

async def cmd_activate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ Ruxsat yo'q.")
        return
    if ctx.args:
        target = ctx.args[0]
        result = await db_patch("shops", f"telegram_id=eq.{target}", {"active": True})
        shops = await db_get("shops", f"telegram_id=eq.{target}&limit=1")
        name = shops[0]["name"] if shops else target
        await update.message.reply_text(f"✅ {name} faollashtirildi!")
        try:
            await ctx.bot.send_message(int(target), "🎉 Hisobingiz faollashtirildi! /start bosing.", reply_markup=main_menu())
        except:
            pass
    else:
        await update.message.reply_text("Format: /activate 1234567890")

async def cmd_deactivate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ Ruxsat yo'q.")
        return
    if ctx.args:
        target = ctx.args[0]
        await db_patch("shops", f"telegram_id=eq.{target}", {"active": False})
        await update.message.reply_text(f"❌ {target} o'chirildi.")
    else:
        await update.message.reply_text("Format: /deactivate 1234567890")

async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ Ruxsat yo'q.")
        return
    shops = await db_get("shops", "select=*&order=created_at.desc")
    if not shops or not isinstance(shops, list):
        await update.message.reply_text("Hali dukon yo'q.")
        return
    text = "🏪 *Barcha dukonlar:*\n\n"
    for s in shops:
        icon = "✅" if s.get("active") else "⏳"
        tid = s.get("telegram_id") or "NULL"
        text += f"{icon} *{s['name']}* — `{tid}`\n"
        if tid and tid != "NULL":
            text += f"   /activate {tid}\n"
            text += f"   /deactivate {tid}\n"
        text += "\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid = str(update.effective_user.id)
    uid = update.effective_user.id
    text = update.message.text.strip()
    state = user_states.get(tid)

    # Admin ham asosiy menyudan foydalana oladi
    if is_admin(uid):
        shop = await get_shop(tid)
        if not shop:
            # Admin uchun avtomatik shop yaratish
            await db_post("shops", {
                "name": "Admin Shop",
                "telegram_id": tid,
                "owner_email": f"{tid}@admin.com",
                "password_hash": "",
                "active": True
            })
            shop = await get_shop(tid)
        if shop and text in ["📊 Bosh sahifa", "📋 Ombor", "➕ Kirim", "🛍️ Sotuv", "📜 Tarix", "ℹ️ Hisob"]:
            await handle_menu(update, ctx, shop, tid, text, state)
            return

    # Registration
    if state == "reg_nom":
        existing = await db_get("shops", f"name=eq.{text}&limit=1")
        if existing and isinstance(existing, list) and existing:
            await update.message.reply_text("⚠️ Bu nom band. Boshqa nom:")
            return
        await db_post("shops", {
            "name": text,
            "telegram_id": tid,
            "owner_email": f"{tid}@tg.com",
            "password_hash": "",
            "active": False
        })
        user_states.pop(tid, None)
        await update.message.reply_text(
            f"✅ *{text}* ro'yxatdan o'tdi!\n⏳ Admin faollashtirishi kutilmoqda.\n🆔 ID: `{tid}`",
            parse_mode="Markdown"
        )
        if ADMIN_ID:
            try:
                await ctx.bot.send_message(
                    ADMIN_ID,
                    f"🆕 Yangi ro'yxat:\nDukon: *{text}*\nID: `{tid}`\nFaollashtirish: /activate {tid}",
                    parse_mode="Markdown"
                )
            except:
                pass
        return

    shop = await get_shop(tid)
    if not shop:
        await start(update, ctx)
        return
    if not shop.get("active"):
        await update.message.reply_text("⏳ Hisobingiz faol emas. Admin kutilmoqda.")
        return

    await handle_menu(update, ctx, shop, tid, text, state)

async def handle_menu(update, ctx, shop, tid, text, state):
    if text == "📊 Bosh sahifa":
        await show_bosh(update, shop)
    elif text == "📋 Ombor":
        await show_ombor(update, shop)
    elif text == "➕ Kirim":
        await show_kirim(update, shop, tid)
    elif text == "🛍️ Sotuv":
        await show_sotuv(update, shop, tid)
    elif text == "📜 Tarix":
        await show_tarix(update, shop)
    elif text == "ℹ️ Hisob":
        await update.message.reply_text(
            f"ℹ️ *Hisob*\n\n🏪 {shop['name']}\n🆔 `{shop['telegram_id']}`\n✅ Faol",
            parse_mode="Markdown"
        )
    elif isinstance(state, dict):
        step = state.get("step")
        if step == "model_nom":
            user_states[tid] = {**state, "step": "model_olcham", "nom": text}
            await update.message.reply_text("📐 O'lchamini yozing (3-4 yosh, S/M/L yoki `-` o'tkazib yuborish):")
        elif step == "model_olcham":
            olcham = "" if text == "-" else text
            user_states[tid] = {**state, "step": "model_ranglar", "olcham": olcham}
            await update.message.reply_text(
                "🎨 Ranglar va pochkalarni yozing:\n\n`Qizil - 5\nKo'k - 3\nSariq - 8`\n\nHar qatorga bitta!",
                parse_mode="Markdown"
            )
        elif step == "model_ranglar":
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            ranglar = []
            error = None
            for line in lines:
                if " - " in line:
                    parts = line.split(" - ", 1)
                    try:
                        ranglar.append({"rang": parts[0].strip(), "stock": int(parts[1].strip())})
                    except:
                        error = line; break
                else:
                    error = line; break
            if error or not ranglar:
                await update.message.reply_text(f"⚠️ Format noto'g'ri: `{error}`\n\nMasalan: `Qizil - 5`", parse_mode="Markdown")
                return
            mid = state.get("model_id")
            if mid:
                for r in ranglar:
                    await db_post("ranglar", {"model_id": mid, "rang": r["rang"], "stock": r["stock"], "sotildi": 0})
            else:
                model_data = await db_post("models", {"shop_id": shop["id"], "nom": state["nom"], "olcham": state.get("olcham", "")})
                mid = model_data[0]["id"]
                for r in ranglar:
                    await db_post("ranglar", {"model_id": mid, "rang": r["rang"], "stock": r["stock"], "sotildi": 0})
            user_states.pop(tid, None)
            rang_text = "\n".join([f"  • {r['rang']}: {r['stock']}pk" for r in ranglar])
            await update.message.reply_text(
                f"✅ *{state['nom']}* qo'shildi!\n\n{rang_text}",
                parse_mode="Markdown", reply_markup=main_menu()
            )
        elif step == "add_stock":
            try:
                soni = int(text)
                r = state["rang"]
                await db_patch("ranglar", f"id=eq.{r['id']}", {"stock": r["stock"] + soni})
                user_states.pop(tid, None)
                await update.message.reply_text(
                    f"✅ {soni}pk qo'shildi! Jami: {r['stock']+soni}pk",
                    reply_markup=main_menu()
                )
            except:
                await update.message.reply_text("⚠️ Son kiriting!")
        elif step == "sotuv_soni":
            try:
                soni = int(text)
                r = state["rang"]
                if r["stock"] < soni:
                    await update.message.reply_text(f"⚠️ Faqat {r['stock']}pk bor!")
                    return
                sana = state.get("sana", today())
                await db_post("sales", {"shop_id": shop["id"], "rang_id": r["id"], "soni": soni, "sana": sana})
                await db_patch("ranglar", f"id=eq.{r['id']}", {"stock": r["stock"]-soni, "sotildi": r["sotildi"]+soni})
                user_states.pop(tid, None)
                qoldi = r["stock"] - soni
                warn = f"\n⚠️ Faqat {qoldi}pk qoldi!" if qoldi <= 3 else ""
                await update.message.reply_text(
                    f"✅ Saqlandi!\n*{state['model_nom']}* — {r['rang']}: {soni}pk{warn}",
                    parse_mode="Markdown", reply_markup=main_menu()
                )
            except:
                await update.message.reply_text("⚠️ Son kiriting!")
        elif step == "sotuv_sana":
            try:
                if "." in text:
                    p = text.split(".")
                    sana = f"{p[2]}-{p[1].zfill(2)}-{p[0].zfill(2)}"
                else:
                    sana = text
                date.fromisoformat(sana)
                user_states[tid] = {**state, "step": "sotuv_soni", "sana": sana}
                r = state["rang"]
                await update.message.reply_text(f"📦 {state['model_nom']} — {r['rang']}\nNechta pochka? ({sana})")
            except:
                await update.message.reply_text("⚠️ Sana noto'g'ri! Masalan: 17.05.2026")
    else:
        await update.message.reply_text("Quyidagilardan birini tanlang:", reply_markup=main_menu())

async def show_bosh(update, shop):
    models = await db_get("models", f"shop_id=eq.{shop['id']}&select=*,ranglar(*)")
    sales = await db_get("sales", f"shop_id=eq.{shop['id']}&sana=gte.{week_ago()}&select=soni,sana")
    if not isinstance(models, list): models = []
    if not isinstance(sales, list): sales = []
    jami = sum(r["stock"] for m in models for r in m.get("ranglar", []))
    bugun = sum(s["soni"] for s in sales if s["sana"] == today())
    hafta = sum(s["soni"] for s in sales)
    top = sorted(models, key=lambda m: sum(r["sotildi"] for r in m.get("ranglar", [])), reverse=True)[:3]
    top_text = "\n".join([f"  {i+1}. {m['nom']} — {sum(r['sotildi'] for r in m.get('ranglar',[]))}pk" for i,m in enumerate(top)]) or "  Hali sotuv yo'q"
    kam = [(m["nom"], r["rang"], r["stock"]) for m in models for r in m.get("ranglar", []) if r["stock"] <= 3]
    kam_text = "\n".join([f"  ⚠️ {n} — {rn}: {s}pk" for n,rn,s in kam[:8]]) or "  Hammasi yetarli ✅"
    await update.message.reply_text(
        f"📊 *{shop['name']}*\n\n📦 Jami: *{jami}pk*\n🛍️ Bugun: *{bugun}pk* | Hafta: *{hafta}pk*\n🗂️ Modellar: *{len(models)}*\n\n🏆 *Top:*\n{top_text}\n\n⚠️ *Kam qolgan:*\n{kam_text}",
        parse_mode="Markdown"
    )

async def show_ombor(update, shop):
    models = await db_get("models", f"shop_id=eq.{shop['id']}&select=*,ranglar(*)")
    if not isinstance(models, list) or not models:
        await update.message.reply_text("📋 Hali model yo'q.")
        return
    text = f"📋 *{shop['name']} — Ombor*\n\n"
    for m in models:
        ranglar = m.get("ranglar", [])
        jami = sum(r["stock"] for r in ranglar)
        text += f"👕 *{m['nom']}*"
        if m.get("olcham"): text += f" ({m['olcham']})"
        text += f" — {jami}pk\n"
        for r in sorted(ranglar, key=lambda x: x["stock"], reverse=True):
            icon = "🔴" if r["stock"]==0 else "🟡" if r["stock"]<=3 else "🟢"
            text += f"  {icon} {r['rang']}: *{r['stock']}pk*\n"
        text += "\n"
        if len(text) > 3500:
            await update.message.reply_text(text, parse_mode="Markdown")
            text = ""
    if text.strip():
        await update.message.reply_text(text, parse_mode="Markdown")

async def show_kirim(update, shop, tid):
    models = await db_get("models", f"shop_id=eq.{shop['id']}&select=id,nom,olcham&order=created_at.desc&limit=20")
    if not isinstance(models, list): models = []
    buttons = [[InlineKeyboardButton("🆕 Yangi model qo'shish", callback_data="new_model")]]
    for m in models:
        label = f"➕ {m['nom']}"
        if m.get("olcham"): label += f" ({m['olcham']})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"mk_{m['id']}")])
    await update.message.reply_text("➕ *Kirim*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def show_sotuv(update, shop, tid):
    models = await db_get("models", f"shop_id=eq.{shop['id']}&select=id,nom,olcham&order=created_at.desc&limit=20")
    if not isinstance(models, list) or not models:
        await update.message.reply_text("⚠️ Hali model yo'q.")
        return
    buttons = []
    for m in models:
        label = f"🛍️ {m['nom']}"
        if m.get("olcham"): label += f" ({m['olcham']})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"ms_{m['id']}")])
    await update.message.reply_text("🛍️ *Sotuv — qaysi model?*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def show_tarix(update, shop):
    sales = await db_get("sales", f"shop_id=eq.{shop['id']}&select=soni,sana,ranglar(rang,models(nom,olcham))&order=created_at.desc&limit=30")
    if not isinstance(sales, list) or not sales:
        await update.message.reply_text("📜 Tarix yo'q.")
        return
    text = "📜 *So'nggi 30 sotuv*\n\n"
    for s in sales:
        r = s.get("ranglar") or {}
        m = r.get("models") or {}
        text += f"📅 {s['sana']} | *{m.get('nom','')}*"
        if m.get("olcham"): text += f" ({m['olcham']})"
        text += f" — {r.get('rang','')}: {s['soni']}pk\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tid = str(query.from_user.id)
    uid = query.from_user.id
    data = query.data
    shop = await get_shop(tid)
    if not shop or (not shop.get("active") and not is_admin(uid)):
        await query.message.reply_text("❌ Hisob faol emas.")
        return

    if data == "new_model":
        user_states[tid] = {"step": "model_nom"}
        await query.message.reply_text("📝 Yangi model nomini yozing:")
    elif data.startswith("mk_"):
        mid = data[3:]
        models = await db_get("models", f"id=eq.{mid}&select=nom,olcham,ranglar(*)")
        if not isinstance(models, list) or not models: return
        model = models[0]
        ranglar = model.get("ranglar", [])
        buttons = [[InlineKeyboardButton(f"➕ {r['rang']} — {r['stock']}pk", callback_data=f"ar_{r['id']}")] for r in ranglar]
        buttons.append([InlineKeyboardButton("🆕 Yangi rang", callback_data=f"nr_{mid}")])
        nom = model["nom"] + (f" ({model['olcham']})" if model.get("olcham") else "")
        await query.message.reply_text(f"➕ *{nom}*\nQaysi rangga?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("ar_"):
        rid = data[3:]
        rangs = await db_get("ranglar", f"id=eq.{rid}&select=*,models(nom)")
        if not isinstance(rangs, list) or not rangs: return
        r = rangs[0]
        model_nom = (r.get("models") or {}).get("nom", "")
        user_states[tid] = {"step": "add_stock", "rang": r, "model_nom": model_nom}
        await query.message.reply_text(f"📦 *{model_nom}* — {r['rang']} ({r['stock']}pk)\nNechta pochka?", parse_mode="Markdown")
    elif data.startswith("nr_"):
        mid = data[3:]
        models = await db_get("models", f"id=eq.{mid}&select=nom,olcham")
        if not isinstance(models, list) or not models: return
        model = models[0]
        user_states[tid] = {"step": "model_ranglar", "nom": model["nom"], "olcham": model.get("olcham",""), "model_id": mid}
        await query.message.reply_text("🎨 Yangi ranglar:\n`Qizil - 5\nKo'k - 3`", parse_mode="Markdown")
    elif data.startswith("ms_"):
        mid = data[3:]
        models = await db_get("models", f"id=eq.{mid}&select=nom,olcham,ranglar(*)")
        if not isinstance(models, list) or not models: return
        model = models[0]
        ranglar = [r for r in model.get("ranglar", []) if r["stock"] > 0]
        if not ranglar:
            await query.message.reply_text("⚠️ Stock yo'q.")
            return
        buttons = [[InlineKeyboardButton(f"🔵 {r['rang']} — {r['stock']}pk", callback_data=f"sr_{r['id']}")] for r in ranglar]
        nom = model["nom"] + (f" ({model['olcham']})" if model.get("olcham") else "")
        await query.message.reply_text(f"🛍️ *{nom}*\nQaysi rang?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("sr_"):
        rid = data[3:]
        rangs = await db_get("ranglar", f"id=eq.{rid}&select=*,models(nom,olcham)")
        if not isinstance(rangs, list) or not rangs: return
        r = rangs[0]
        m = r.get("models") or {}
        model_nom = m.get("nom","") + (f" ({m['olcham']})" if m.get("olcham") else "")
        buttons = [
            [InlineKeyboardButton("📅 Bugun", callback_data=f"st_{rid}")],
            [InlineKeyboardButton("📓 Boshqa sana", callback_data=f"sd_{rid}")]
        ]
        await query.message.reply_text(f"🛍️ *{model_nom}* — {r['rang']}\nQachon?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("st_"):
        rid = data[3:]
        rangs = await db_get("ranglar", f"id=eq.{rid}&select=*,models(nom,olcham)")
        if not isinstance(rangs, list) or not rangs: return
        r = rangs[0]
        m = r.get("models") or {}
        model_nom = m.get("nom","") + (f" ({m['olcham']})" if m.get("olcham") else "")
        user_states[tid] = {"step": "sotuv_soni", "rang": r, "model_nom": model_nom, "sana": today()}
        await query.message.reply_text(f"📦 *{model_nom}* — {r['rang']} ({r['stock']}pk)\nNechta pochka?", parse_mode="Markdown")
    elif data.startswith("sd_"):
        rid = data[3:]
        rangs = await db_get("ranglar", f"id=eq.{rid}&select=*,models(nom,olcham)")
        if not isinstance(rangs, list) or not rangs: return
        r = rangs[0]
        m = r.get("models") or {}
        model_nom = m.get("nom","") + (f" ({m['olcham']})" if m.get("olcham") else "")
        user_states[tid] = {"step": "sotuv_sana", "rang": r, "model_nom": model_nom}
        await query.message.reply_text("📅 Sanani yozing (masalan: 17.05.2026):")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("activate", cmd_activate))
    app.add_handler(CommandHandler("deactivate", cmd_deactivate))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print(f"✅ Bot ishga tushdi! ADMIN_ID={ADMIN_ID}")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
