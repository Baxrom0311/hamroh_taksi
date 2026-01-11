import psycopg2

try:
    conn = psycopg2.connect(
        host="192.168.1.7",     # masalan: 
        port=5432,
        dbname="hamroh_bot",
        user="hamroh_user",
        password="root"
    )
    cur = conn.cursor()
    cur.execute("SELECT 1;")
    print("✅ DATABASE GA ULANISH MUVAFFAQIYATLI")
    conn.close()
except Exception as e:
    print("❌ ULANISHDA XATOLIK:")
    print(e)
