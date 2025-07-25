import streamlit as st
from pypdf import PdfReader
import pandas as pd
import io
import os
import math
import re
from openai import OpenAI
from io import BytesIO

client = OpenAI(api_key=st.secrets["openai_api_key"])

astm_standards = {
    "Electrical Resistivity Test (ERT)": "ASTM G57",
    "Seismic Refraction Test (SRT)": "ASTM D5777",
    "Atterberg Limit Test": "ASTM D4318",
    "Sieve Analysis": "ASTM D6913",
    "UCS Test - Soil": "ASTM D2166",
    "UCS Test - Rock": "ASTM D7012",
    "Oedometer Test": "ASTM D2435",
    "Direct Shear Test": "ASTM D3080",
    "Collapse Test": "ASTM D5333",
    "California Bearing Ratio": "ASTM D1883",
    "Proctor Test": "ASTM D698"
}

corrosion_classes = [
    (100, float('inf'), "Низкое", "Очень слабая коррозия"),
    (50.01, 100, "Слабо коррозионный", "Слабо коррозионный"),
    (20.01, 50, "Слабо коррозионный", "Умеренно коррозионный"),
    (10.01, 20, "Умеренно коррозионный", "Высококоррозионный"),
    (5.01, 10, "Коррозионно-активный", "Чрезвычайно коррозионный"),
    (0, 5, "Высококоррозионный", "Чрезвычайно коррозионный"),
]

corrosion_colors = {
    "Низкое": "#d0f0c0",
    "Очень слабая коррозия": "#d0f0c0",
    "Слабо коррозионный": "#fef3bd",
    "Умеренно коррозионный": "#ffd59e",
    "Коррозионно-активный": "#ffadad",
    "Высококоррозионный": "#ff6b6b",
    "Чрезвычайно коррозионный": "#ff6b6b",
    "Out of range": "#cccccc",
    "Invalid": "#e0e0e0"
}

def classify_corrosion(resistivity_ohm_m):
    try:
        val = float(resistivity_ohm_m)
        for low, high, nace, astm in corrosion_classes:
            if low <= val <= high:
                return nace, astm
        return "Out of range", "Out of range"
    except:
        return "Invalid", "Invalid"

def extract_text_from_pdf(pdf_file):
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

def format_float(val):
    try:
        return f"{round(float(str(val).replace(',', '.')), 2):.2f}"
    except:
        return "-"

def ask_gpt_astm_analysis(test_name, extracted_text, model_name, language_code):
    standard = astm_standards.get(test_name, "соответствующий ASTM стандарт")
    prompt = f'''
You are a geotechnical assistant.

Given the lab report below for the "{test_name}" test, do the following:

1. Extract a clean data table with the following columns:
   - № п/п
   - № Выработки
   - Расстояние между электродами, а (м)
   - Показание прибора R (Ом)
   - Удельное сопротивление ρ = 2πRa (Ом·м)
   - Коррозионная агрессивность по NACE
   - Коррозионная активность по ASTM

2. All numeric values must be formatted with 2 decimal places. Use "-" for missing or non-numeric data.

3. Then provide a short summary below the table that clearly lists:
   - Which values or columns are missing or incomplete.
   - What ASTM-required parameters are missing or improperly reported according to {standard}.

Use language: {language_code.upper()}.

Report:
"""{extracted_text}"""
'''
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ GPT error: {e}"

def parse_distance_to_meters(raw_value):
    val = raw_value.lower().strip().replace(",", ".")
    if re.search(r"(см|cm)", val):
        number = re.findall(r"[\d\.]+", val)
        if number:
            return round(float(number[0]) / 100, 4)
    try:
        fval = float(val)
        if fval > 10:
            return round(fval / 100, 4)
        return round(fval, 4)
    except:
        return None

def gpt_response_to_table(response):
    lines = [line for line in response.strip().split("\n") if line.strip()]
    table_lines = [line for line in lines if "|" in line and not re.match(r"^\s*-{2,}", line)]

    data = []
    for line in table_lines:
        parts = [p.strip() for p in line.strip("- ").split("|") if p.strip()]
        if len(parts) < 5:
            continue

        number = parts[0] if len(parts) > 0 else "-"
        well_no = parts[1] if len(parts) > 1 else "-"
        a_raw = parts[2] if len(parts) > 2 else "-"
        r_val = parts[3] if len(parts) > 3 else "-"
        resistivity_val = parts[4] if len(parts) > 4 else "-"

        a_meters = parse_distance_to_meters(a_raw)
        a_val = format_float(a_meters) if a_meters is not None else "-"

        try:
            r_float = float(r_val.replace(",", "."))
        except:
            r_float = None

        try:
            rho_float = float(resistivity_val.replace(",", "."))
        except:
            rho_float = None

        if (rho_float is None or rho_float < 20) and r_float and a_meters:
            resistivity_val = format_float(2 * math.pi * r_float * a_meters)
        else:
            resistivity_val = format_float(rho_float)

        nace, astm = classify_corrosion(resistivity_val)

        data.append([
            number,
            well_no,
            a_val,
            format_float(r_val),
            resistivity_val,
            nace,
            astm
        ])

    df = pd.DataFrame(data, columns=[
        "№ п/п",
        "№ Выработки",
        "Расстояние между электродами а, (м)",
        "Показание прибора R, (Ом)",
        "Удельное электрическое сопротивление ρ=2πRa Ом·м",
        "Коррозионная агрессивность по NACE",
        "Коррозионная активность по ASTM"
    ])
    return df

def analyze_missing_data(df):
    missing_info = []
    for row_idx, row in df.iterrows():
        for col in df.columns:
            val = str(row[col]).strip().lower()
            if val in ["-", "nan", "", "none"]:
                missing_info.append(f"🚫 Пропущено в строке {row_idx + 1}, колонка '{col}'")
    return missing_info

def style_table(df):
    def nace_color(val):
        return f"background-color: {corrosion_colors.get(val, '#ffffff')}"
    def astm_color(val):
        return f"background-color: {corrosion_colors.get(val, '#ffffff')}"
    def missing_highlight(val):
        if str(val).strip().lower() in ["-", "nan", "", "none"]:
            return "background-color: #f0f0f0; color: #a00"
        return ""
    return df.style \
        .applymap(nace_color, subset=["Коррозионная агрессивность по NACE"]) \
        .applymap(astm_color, subset=["Коррозионная активность по ASTM"]) \
        .applymap(missing_highlight)

# Интерфейс
st.set_page_config(page_title="Geotechnical Test Validator", layout="wide")
st.title("🧪 Geotechnical Test Result Checker")

lang = st.sidebar.selectbox("🌐 Выберите язык:", ["Русский", "O'zbek", "English"])
lang_codes = {"Русский": "ru", "O'zbek": "uz", "English": "en"}
language_code = lang_codes[lang]

model_choice = st.sidebar.selectbox(
    "🤖 Выберите модель Juru AI:",
    ["gpt-4-turbo", "gpt-3.5-turbo"],
    index=0
)

st.markdown("📄 Загрузите PDF лабораторного протокола и выберите тип теста. GPT проверит соответствие ASTM и покажет таблицу с анализом.")

test_types = list(astm_standards.keys())
tabs = st.tabs(test_types)

for i, test_name in enumerate(test_types):
    with tabs[i]:
        st.header(f"{test_name}")
        uploaded_file = st.file_uploader(f"📎 Загрузите PDF для {test_name}", type="pdf", key=test_name)

        if uploaded_file:
            with st.spinner("📖 Обработка PDF..."):
                text = extract_text_from_pdf(uploaded_file)
                st.success("✅ PDF успешно загружен и обработан.")

            st.subheader("🤖 Анализ JURU AI")
            gpt_response = ask_gpt_astm_analysis(test_name, text, model_choice, language_code)
            df_result = gpt_response_to_table(gpt_response)

            st.dataframe(style_table(df_result), use_container_width=True)

            # Пропущенные значения
            missing_entries = analyze_missing_data(df_result)
            if missing_entries:
                st.subheader("❗ Пропущенные данные:")
                for msg in missing_entries:
                    st.markdown(f"- {msg}")
            else:
                st.success("✅ Все значения присутствуют.")

            # Вывод комментариев GPT как текст
            extra_lines = gpt_response.strip().splitlines()
            comment_lines = [line for line in extra_lines if not "|" in line and not re.match(r"^\s*№", line)]
            if comment_lines:
                st.markdown("### 🧠 Комментарии от JURU AI:")
                for line in comment_lines:
                    st.markdown(f"- {line}")

            # Скачивание Excel
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                df_result.to_excel(writer, index=False, sheet_name='GPT Analysis')

            st.download_button(
                label="📊 Скачать Excel-отчёт",
                data=excel_buffer,
                file_name=f"{test_name.replace(' ', '_')}_GPT_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
