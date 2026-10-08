import csv
import os
import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ==========================================
# ⚙️ НАСТРОЙКИ СКРИПТА
# ==========================================
INPUT_FILE = 'ИНН организаций отдыха детей и их оздоровления - Лист1.csv'
OUTPUT_FILE = 'report_licenses.csv'
HEADLESS = False          # False = видно браузер, True = скрыто (быстрее)
DELAY = 2.5               # Пауза между запросами (сек), чтобы не забанили
# ==========================================

# Настройка кодировки для корректного вывода эмодзи в консоли
sys.stdout.reconfigure(encoding='utf-8')

def load_processed_inns():
    """Читает файл отчета и возвращает список уже проверенных ИНН"""
    if not os.path.exists(OUTPUT_FILE):
        return set()
    processed = set()
    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader, None) # Пропускаем заголовок
            for row in reader:
                if row and row[0].strip():
                    processed.add(row[0].strip())
    except Exception:
        pass
    return processed

def check_license(inn: str, page) -> str:
    """Проверяет наличие лицензии для одного ИНН"""
    try:
        # 1. Находим поле ввода
        inn_field = page.locator("#id_q_no")
        
        # 2. Очищаем поле и вводим ИНН (имитация печати)
        inn_field.fill("")
        time.sleep(0.3)
        inn_field.type(inn, delay=30)
        
        # 3. Нажимаем Enter для поиска (самый надежный способ)
        inn_field.press("Enter")
        
        # 4. Ждем загрузки результатов
        # Используем try/except, так как AJAX-запросы не всегда триггерят networkidle
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeout:
            pass 
        
        # Дополнительная пауза для отрисовки таблицы
        time.sleep(2)
        
        # 5. Анализируем содержимое страницы
        content = page.content().lower()
        
        # Ищем фразы, указывающие на отсутствие результатов
        if any(phrase in content for phrase in [
            "не найдено", 
            "ничего не найдено", 
            "сведений не найдено", 
            "поиск не дал результатов",
            "по заданным параметрам"
        ]):
            return "❌ Нет лицензии"
            
        # Ищем наличие таблицы с данными (строки в tbody)
        rows = page.locator("table tbody tr").count()
        if rows > 0:
            return "✅ Лицензия найдена"
            
        return "❓ Неопределено (нет данных)"
        
    except PlaywrightTimeout:
        return "⏱ Таймаут"
    except Exception:
        return "⛔ Ошибка скрипта"

def main():
    print(f"📂 Путь к файлу ИНН: {os.path.abspath(INPUT_FILE)}")
    
    # 1. Проверка наличия входного файла
    if not os.path.exists(INPUT_FILE):
        print(f"❌ ОШИБКА: Файл '{INPUT_FILE}' не найден!")
        print("💡 Убедись, что файл лежит в той же папке, что и скрипт.")
        return

    # 2. Чтение списка ИНН
    inns = []
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader, None)  # Пропуск заголовка
            for row in reader:
                if row and row[0].strip():
                    inns.append(row[0].strip())
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")
        return

    # 3. Фильтрация уже проверенных
    processed = load_processed_inns()
    inns_to_check = [inn for inn in inns if inn not in processed]
    
    print(f"📊 Всего в списке: {len(inns)}")
    print(f"✅ Уже проверено: {len(processed)}")
    print(f"🔄 Осталось проверить: {len(inns_to_check)}")
    
    if not inns_to_check:
        print("🎉 Все организации уже проверены! Отчет актуален.")
        return

    # 4. Запуск браузера и проверка
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=HEADLESS,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.new_page()
            page.set_default_timeout(15000) # Таймаут действий 15 сек
            
            print("🌐 Открываем сайт Росздравнадзора...")
            page.goto("https://roszdravnadzor.gov.ru/services/licenses")
            time.sleep(2) # Ждем полной прогрузки JS
            
            # Открываем файл для дозаписи
            file_exists = os.path.exists(OUTPUT_FILE)
            needs_header = not file_exists or os.path.getsize(OUTPUT_FILE) == 0
            
            with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8-sig') as out_f:
                writer = csv.writer(out_f)
                if needs_header:
                    writer.writerow(["ИНН", "Статус", "Время"])
                
                # Цикл проверки
                for i, inn in enumerate(inns_to_check, 1):
                    print(f"[{i}/{len(inns_to_check)}] 🔍 {inn} ...", end=" ", flush=True)
                    
                    status = check_license(inn, page)
                    
                    # Записываем результат
                    writer.writerow([inn, status, time.strftime("%H:%M:%S")])
                    out_f.flush() # 🚀 ВАЖНО: Мгновенно сохраняем на диск
                    
                    print(status)
                    time.sleep(DELAY)
                    
    except KeyboardInterrupt:
        print("\n⏹️ Работа остановлена пользователем (Ctrl+C).")
        print("✅ Прогресс сохранен. При повторном запуске продолжим с места остановки.")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
    finally:
        if browser:
            browser.close()
        
        print("\n" + "="*40)
        print(f"🏁 Готово! Отчет сохранен в:")
        print(f"📄 {os.path.abspath(OUTPUT_FILE)}")
        print("="*40)

if __name__ == "__main__":
    main()