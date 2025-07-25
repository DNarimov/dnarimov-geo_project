import streamlit as st
from pypdf import PdfReader
import pandas as pd
import math
import re
from openai import OpenAI
from io import BytesIO

client = OpenAI(api_key=st.secrets["openai_api_key"])

# Перевод колонок по языку
column_translations = {
    "ru": [
        "№ п/п",
        "№ Выработки",
        "Расстояние между электродами а, (м)",
        "Показание прибора R, (Ом)",
        "Удельное электрическое сопротивление ρ=2πRa Ом·м",
        "Коррозионная агрессивность по NACE",
        "Коррозионная активность по ASTM"
    ],
    "en": [
        "No.",
        "Test Point",
        "Electrode Spacing a, (m)",
        "Instrument Reading R (Ohm)",
        "Resistivity ρ = 2πRa (Ohm·m)",
        "Corrosion Class (NACE)",
        "Corrosion Activity (ASTM)"
    ],
    "uz": [
        "№",
        "Ish joyi",
        "Elektrodlar orasidagi masofa a, (m)",
        "Asbob ko'rsatkichi R (Om)",
        "Xususiy qarshilik ρ = 2πRa (Om·m)",
        "Korroziya klassi (NACE)",
        "Korroziya faolligi (ASTM)"
    ]
}

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

def format_float(val):
    try:
        return f"{round(float(str(val).replace(',', '.')), 2):.2f}"
    except:
        return "-"

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

def extract_text_from_pdf(pdf_file):
    reader = PdfReader(pdf_file)
    return "".join([page.extract_text() or "" for page in reader.pages])

def ask_gpt_astm_analysis(test_name, extracted_text, model_name, language_code):
    standard = astm_standards.get(test_name, "соответствующий ASTM стандарт")
    prompt = f'''
You are a geotechnical assistant.

From the report below for the "{test_name}" test, perform the following:

1. Extract ALL rows from any tabular data related to this test. Do not skip repeated or similar values.

2. Build a table with these columns:
   - № п/п
   - № Выработки
   - Расстояние между электродами, а (м)
   - Показание прибора R (Ом)
   - Удельное сопротивление ρ = 2πRa (Ом·м)
   - Коррозионная агрессивность по NACE
   - Коррозионная активность по ASTM

3. Use 2 decimal places for all numeric values. If missing — write "-".

4. Then give a plain-language summary:
   - Which values were missing and auto-calculated.
   - Which ASTM-required parameters were not present.
   - Final conclusion: full compliance / partial compliance / major errors.

Use language: {language_code.upper()}.
Report:
"""{extracted_text}"""
'''
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ GPT error: {e}"

def gpt_response_to_table(response, language_code):
    lines = [line for line in response.strip().split("\n") if line.strip()]
    table_lines = []
    for line in lines:
        if "|" in line and "№" not in line and "---" not in line and "..." not in line:
            table_lines.append(line)

    data = []
    for line in table_lines:
        parts = [p.strip() for p in line.strip("- ").split("|") if p.strip()]
        if len(parts) < 5:
            continue

        number = parts[0]
        well_no = parts[1]
        a_raw = parts[2]
        r_val = parts[3]
        resistivity_val = parts[4]

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

    return pd.DataFrame(data, columns=column_translations.get(language_code, column_translations["ru"]))

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
        .applymap(nace_color, subset=df.columns[-2:-1]) \
        .applymap(astm_color, subset=df.columns[-1:]) \
        .applymap(missing_highlight)

# === Интерфейс ===
st.set_page_config(page_title="Geotechnical Test Validator", layout="wide")
st.title("Geotechnical Test Result Checker")

lang = st.sidebar.selectbox("🌐 Выберите язык:", ["Русский", "O'zbek", "English"])
lang_codes = {"Русский": "ru", "O'zbek": "uz", "English": "en"}
language_code = lang_codes[lang]

model_choice = st.sidebar.selectbox("Модель Juru AI:", ["gpt-4-turbo", "gpt-3.5-turbo"], index=0)

st.markdown("📄 Загрузите PDF лабораторного протокола и выберите тип теста. GPT проверит соответствие ASTM и покажет таблицу с анализом.")

for test_name in astm_standards:
    with st.expander(test_name):
        uploaded_file = st.file_uploader(f"Загрузите PDF для {test_name}", type="pdf", key=test_name)

        if uploaded_file:
            with st.spinner("Извлечение данных..."):
                text = extract_text_from_pdf(uploaded_file)

            st.subheader("Результаты анализа:")
            gpt_response = ask_gpt_astm_analysis(test_name, text, model_choice, language_code)
            df = gpt_response_to_table(gpt_response, language_code)
            st.dataframe(style_table(df), use_container_width=True)

            # Комментарии от GPT
            lines = gpt_response.strip().splitlines()
            comment_lines = []
            table_started = False
            for line in lines:
                if "|" in line and "№" in line:
                    table_started = True
                    continue
                if table_started and "|" not in line and len(line.strip()) > 3:
                    comment_lines.append(line.strip())

            comment_lines = [
                line for line in comment_lines
                if line and not line.startswith("|") and "===" not in line and "---" not in line
            ]

            if comment_lines:
                st.markdown("### Комментарии от JURU AI:")
                for line in comment_lines:
                    st.markdown(f"- {line}")

                st.markdown("### 📋 Итог по ERT согласно ASTM:")
                for line in comment_lines:
                    if any(x in line.lower() for x in ["summary", "итог", "compliance", "ошибка", "соответствие"]):
                        st.markdown(f"> {line}")

            # Скачать Excel
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("📥 Скачать Excel", data=buffer.getvalue(), file_name="ERT_Report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
