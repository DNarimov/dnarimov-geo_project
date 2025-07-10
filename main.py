import streamlit as st
from pypdf import PdfReader
from fpdf import FPDF
import pandas as pd
import io
import os
from openai import OpenAI
from io import BytesIO

# OpenAI client
client = OpenAI(api_key=st.secrets["openai_api_key"])

# ASTM стандарты
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

# Классификация по удельному сопротивлению грунта
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

# === Функции ===
def classify_corrosion(resistivity_ohm_m):
    try:
        val = float(resistivity_ohm_m)
        for low, high, nace, astm in corrosion_classes:
            if low <= val <= high:
                return nace, astm
        return "Out of range", "Out of range"
    except:
        return "Invalid", "Invalid"

def extract_text_from_pdf(pdf_file, max_chars=10000):
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
        if len(text) > max_chars:
            break
    return text[:max_chars]

def ask_gpt_astm_analysis(test_name, extracted_text, model_name, language_code):
    standard = astm_standards.get(test_name, "соответствующий ASTM стандарт")

    prompt = f'''
You are a technical assistant. Extract and present tabular lab data for the "{test_name}" test from the report below.
Focus on columns:
1. № п/п
2. № Выработки
3. Расстояние между электродами, а (м)
4. Показание прибора R (Ом)
5. Удельное сопротивление ρ = 2πRa (Ом·м)
6. Коррозионная агрессивность по NACE
7. Коррозионная активность по ASTM
If some values are missing, calculate where possible or write "-".
Return only clean table. Use language: {language_code.upper()}.

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

def gpt_response_to_table(response):
    lines = [line for line in response.strip().split("\n") if line.strip() and "№" not in line]
    data = []
    for line in lines:
        parts = line.strip("- ").split("|")
        if len(parts) >= 5:
            number = parts[0].strip()
            well_no = parts[1].strip()
            a_val = parts[2].strip()
            r_val = parts[3].strip()
            resistivity_val = parts[4].strip()
            nace, astm = classify_corrosion(resistivity_val)
            data.append([number, well_no, a_val, r_val, resistivity_val, nace, astm])
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

def style_table(df):
    def nace_color(val):
        return f"background-color: {corrosion_colors.get(val, '#ffffff')}"
    styled = df.style.applymap(nace_color, subset=["Коррозионная агрессивность по NACE"])
    return styled

# === Интерфейс Streamlit ===
st.set_page_config(page_title="Geotechnical Test Validator", layout="wide")
st.title("Geotechnical Test Result Checker")

with st.expander("🌐 Выбор языка"):
    lang = st.sidebar.selectbox("🌐 Выберите язык:", ["Русский", "O'zbek", "English"])
lang_codes = {"Русский": "ru", "O'zbek": "uz", "English": "en"}
language_code = lang_codes[lang]

model_choice = st.sidebar.selectbox(
    "🤖 Выберите модель Juru AI:",
    ["gpt-4-turbo", "gpt-3.5-turbo"],
    index=0,
    help="GPT-4 точнее, GPT-3.5 быстрее и дешевле"
)

st.markdown("Загрузите PDF-файл лабораторного протокола и выберите тип теста. GPT проверит его соответствие ASTM и покажет таблицу с анализом.")

test_types = list(astm_standards.keys())
tabs = st.tabs(test_types)

for i, test_name in enumerate(test_types):
    with tabs[i]:
        st.header(f" {test_name}")
        uploaded_file = st.file_uploader(f"Загрузите PDF для {test_name}", type="pdf", key=test_name)

        if uploaded_file:
            with st.spinner("📄 Обработка PDF..."):
                text = extract_text_from_pdf(uploaded_file)
                st.success("✅ PDF успешно загружен и обработан.")

            st.subheader("🤖 Анализ JURU AI")
            gpt_response = ask_gpt_astm_analysis(test_name, text, model_choice, language_code)
            df_result = gpt_response_to_table(gpt_response)

            st.dataframe(style_table(df_result), use_container_width=True)

            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                df_result.to_excel(writer, index=False, sheet_name='GPT Analysis')

            st.download_button(
                label="📊 Скачать Excel отчёт",
                data=excel_buffer,
                file_name=f"{test_name.replace(' ', '_')}_GPT_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
