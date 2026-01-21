"""
app/bot/messages.py
Centralized messages for the bot.
"""

class Messages:
    class Error:
        USER_NOT_FOUND = "Xatolik: user topilmadi"
        DATA_NOT_FOUND = "Xatolik: ma'lumotlar topilmadi"
        CALLBACK_DATA_MISSING = "Xatolik: data mavjud emas"
        DRIVER_NOT_FOUND = "❌ Haydovchi topilmadi"
        PASSENGER_NOT_FOUND = "❌ Yo'lovchi topilmadi"
        ORDER_NOT_FOUND = "❌ Buyurtma topilmadi"
        ACTIVE_ORDER_NOT_FOUND = "❌ Aktiv buyurtma topilmadi"
        ORDER_BUT_DRIVER_MISMATCH = "❌ Buyurtma topilmadi yoki sizga tegishli emas"
        SOMETHING_WENT_WRONG = "❌ Xatolik yuz berdi"
        MESSAGE_OUTDATED = "⚠️ Bu xabar eskirgan"
        GENERIC = "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
        
        SUPPORT_INFO = (
            "📞 <b>Support xizmati</b>\n\n"
            "Admin bilan bog'lanish: @Bakhromdev\n"
            "Telefon: +998 93 558 03 11\n\n"
            "Ish vaqti: 9:00 - 21:00"
        )
    
    class Driver:
        BLOCKED = "🚫 <b>Siz bloklangansiz!</b>\n\nSabab: {reason}\n\nMurojaat: @support"
        ALREADY_ACTIVE = "⏳ Siz allaqachon buyurtma kutyapsiz"
        ALREADY_ON_TRIP = "⚠️ Siz hozir safardasiz!\n\nAvval safarni yakunlang."
        BALANCE_LOW = (
            "⚠️ <b>Balans yetarli emas!</b>\n\n"
            "Kerak: <b>{required:,} so'm</b>\n"
            "Mavjud: <b>{balance:,} so'm</b>\n\n"
            "💰 Balansni to'ldirish uchun:\n"
            "Menyu → Balans"
        )
        NO_ACTIVE_ROUTES = "❌ Hozirda aktiv marshrutlar yo'q"
        LOCATION_REQUEST = (
            "📍 <b>Locatsiyangizni yuboring</b>\n\n"
            "Buyurtma qabul qilish uchun lokatsiyangizni yuboring.\n\n"
            "📍 Lokatsiyani yuborish tugmasini bosing:"
        )
        QUEUE_JOINED = (
            "✅ <b>Buyurtmalar qabul qilinmoqda!</b>\n\n"
            "📍 Marshrut: <b>{route_name}</b>\n"
            "👥 Bo'sh joylar: <b>{seats}</b>\n\n"
            "⏳ Buyurtma kelishini kutmoqdasiz...\n\n"
            "💡 Buyurtma kelganda sizga xabar beramiz!"
        )
        STOPPED = "✅ Buyurtma qabul qilish to'xtatildi"
        OFFLINE = "Siz oflayn holatga o'tdingiz"
        
        # Order acceptance
        ORDER_ACCEPTED = (
            "✅ <b>Buyurtma #{order_id} qabul qilindi!</b>\n\n"
            "💰 Komissiya: <b>{commission:,} so'm</b>\n"
            "📊 Yangi balans: <b>{new_balance:,} so'm</b>"
        )
        PASSENGER_INFO = (
            "✅ <b>Buyurtma qabul qilindi!</b>\n\n"
            "📍 <b>Olish joyi:</b> {pickup_location}\n"
            "<a href=\"{google_maps_link}\">🗺️ Google Maps</a> | <a href=\"{telegram_location_link}\">📍 Telegram xarita</a>\n"
            "{order_type}\n"
            "📱 <b>Telefon:</b> {phone}"
        )
        TRIP_STARTED = (
            "✅ <b>Yo'lga chiqdingiz!</b>\n\n"
            "📦 Buyurtma #{order_id}\n\n"
            "🚗 Xavfsiz yo'l!\n\n"
            "⏱ Safar 15 daqiqadan keyin avtomatik yakunlanadi.\n"
            "Yoki '<b><i>🚗 Safarni yakunlash</i></b>' tugmasini bosing."
        )
        TRIP_COMPLETED = (
            "🎉 <b>Safar yakunlandi!</b>\n\n"
            "📦 Buyurtma #{order_id}\n"
            "⏱ Davomiyligi: {duration} daqiqa\n\n"
            "✨ Rahmat! Keyingi safarga muvaffaqiyat tilaymiz!"
        )
        ORDER_CANCELLED = (
            "❌ <b>Buyurtma bekor qilindi</b>\n\n"
            "📦 Buyurtma #{order_id}\n\n"
            "⚠️ Warning olindingiz!"
        )
        TRIP_ACCEPTED_PROMPT = "✅ <b>Buyurtma #{order_id} qabul qilindi!</b>"
        REMAINING_SEATS_INFO = "\n\n👥 Qolgan bo'sh joylar: <b>{remaining_seats}</b>"

    class Passenger:
        NO_ROUTES = "❌ Hozirda aktiv marshrutlar yo'q"
        WHERE_TO = "📍 <b>Qayerga borasiz?</b>\n\nMarshrutni tanlang:"
        WHERE_FROM = "📍 <b>Qayerga borishni xohlaysiz?</b>\nLokatsiyangizni yuboring:"
        SEND_LOCATION = "📍 Lokatsiyangizni yuboring:"
        LOCATION_RECEIVED = (
            "✅ Lokatsiya qabul qilindi\n\n"
            "📍 Lokatsiya haqida qo'shimcha ma'lumot yozing:\n"
            "(Masalan: \"Uy oldida\", \"Kafe yonida\", \"Ko'cha 5\")"
        )
        LOCATION_DESC_RECEIVED = (
            "✅ Izoh qabul qilindi\n\n"
            "👥 Necha kishi borasiz yoki pochtami?\n\n"
            "Tanlang:"
        )
        ORDER_CREATED = (
            "✅ <b>Buyurtma qabul qilindi!</b>\n\n"
            "📦 Buyurtma #{order_id}\n\n"
            "⏳ Haydovchi topilmoqda...\n\n"
            "📱 Haydovchi topilgach xabar beramiz!"
        )
        DRIVER_FOUND = (
            "✅ <b>Haydovchi topildi!</b>\n\n"
            "📦 Buyurtma: #{order_id}\n\n"
            "👤 Haydovchi: {full_name}\n"
            "📱 <b>Telefon:</b> {phone_number}\n"
            "🎨 <b>Rang:</b> {car_color}\n"
            "🚗 Mashina: {car_model} ({car_color})\n"
            "🔢 Raqam: {car_number}\n\n"
            "Haydovchi siz tomonga yo'lga chiqdi!"
        )
        
        SELECT_NEW_DRIVER = (
            "🔄 <b>Yangi haydovchi tanlang</b>\n\n"
            "📦 Buyurtma #{order_id}\n\n"
            "Quyidagi haydovchilardan birini tanlang:"
        )

        DRIVER_BANNED = (
            "🚫 <b>Haydovchi ban qilindi</b>\n\n"
            "Admin ko'rib chiqadi.\n"
            "Yangi haydovchi topilmoqda..."
        )
