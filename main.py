import streamlit as st
from pypdf import PdfReader
from fpdf import FPDF
import pandas as pd
import io
import os
from openai import OpenAI

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

# === Извлечение текста из PDF ===
def extract_text_from_pdf(pdf_file, max_chars=10000):
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
        if len(text) > max_chars:
            break
    return text[:max_chars]

# === GPT анализ ASTM ===
def ask_gpt_astm_analysis(test_name, extracted_text, model_name, language_code):
    standard = astm_standards.get(test_name, "соответствующий ASTM стандарт")

    prompt = f'''
You are a technical assistant. In short, clear bullet points, analyze the lab report for **{test_name}**, according to **{standard}**.

Respond in language: {language_code.upper()}.

Output format (no intro or extra text):
- Found parameters (with units and values)
- Missing parameters
- Compliance assessment
- Short recommendations

Report text:
"""{extracted_text}"""
'''

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ GPT error: {e}"

# === Парсинг ответа GPT в таблицу ===
def gpt_response_to_table(response):
    sections = [s.strip("- ").split(":") if ":" in s else [s.strip("- "), ""]
                for s in response.strip().split("\n") if s.strip()]
    df = pd.DataFrame(sections, columns=["Category", "Detail"])
    return df

# === PDF отчёт ===
def generate_pdf_report(test_name, findings_table):
    pdf = FPDF()
    pdf.add_page()

    try:
        font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
        pdf.add_font("DejaVu", "", font_path, uni=True)
        pdf.set_font("DejaVu", size=10)
    except:
        pdf.set_font("Arial", size=10)

    pdf.cell(200, 10, txt=f"Отчёт по тесту: {test_name}", ln=True)

    for index, row in findings_table.iterrows():
        pdf.multi_cell(0, 10, txt=f"{row['Category']}: {row['Detail']}")

    pdf_data = pdf.output(dest='S').encode("utf-8")
    return io.BytesIO(pdf_data)

# === Интерфейс Streamlit ===
st.set_page_config(page_title="Geotechnical Test Validator", layout="wide")
st.title("📊 Geotechnical Test Result Checker")

st.markdown("Загрузите PDF-файл лабораторного протокола и выберите тип теста. GPT проверит его соответствие ASTM.")

# Язык
lang = st.sidebar.selectbox("🌐 Выберите язык:", ["Русский", "O'zbek", "English"])
lang_codes = {"Русский": "ru", "O'zbek": "uz", "English": "en"}
language_code = lang_codes[lang]

# Модель GPT
model_choice = st.sidebar.selectbox(
    "🤖 Выберите модель GPT:",
    ["gpt-4-turbo", "gpt-3.5-turbo"],
    index=0,
    help="GPT-4 точнее, GPT-3.5 быстрее и дешевле"
)

# Tabs по типам тестов
test_types = list(astm_standards.keys())
tabs = st.tabs(test_types)

for i, test_name in enumerate(test_types):
    with tabs[i]:
        st.header(f"🧪 {test_name}")
        uploaded_file = st.file_uploader(f"Загрузите PDF для {test_name}", type="pdf", key=test_name)

        if uploaded_file:
            with st.spinner("📄 Обработка PDF..."):
                text = extract_text_from_pdf(uploaded_file)
                st.success("✅ PDF успешно загружен и обработан.")

            st.subheader("🤖 Анализ JURU AI")
            gpt_response = ask_gpt_astm_analysis(test_name, text, model_choice, language_code)
            st.markdown(gpt_response)

            df_result = gpt_response_to_table(gpt_response)
            st.dataframe(df_result)

            # Excel download
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                df_result.to_excel(writer, index=False, sheet_name='GPT Analysis')

            st.download_button(
                label="📊 Скачать Excel отчёт",
                data=excel_buffer,
                file_name=f"{test_name.replace(' ', '_')}_GPT_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # PDF download
            pdf_file = generate_pdf_report(test_name, df_result)
            st.download_button(
                label="📄 Скачать PDF отчёт",
                data=pdf_file,
                file_name=f"{test_name.replace(' ', '_')}_GPT_Report.pdf",
                mime="application/pdf"
            )
