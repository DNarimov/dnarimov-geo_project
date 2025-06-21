import streamlit as st
from pypdf import PdfReader
from fpdf import FPDF
import io
import os
from openai import OpenAI  # Новый импорт

# Загружаем API-ключ
client = OpenAI(api_key=st.secrets["openai_api_key"])

# Сопоставление тестов со стандартами ASTM
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

# ====== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======
def extract_text_from_pdf(pdf_file):
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

def display_test_result(test_name, text):
    st.subheader(f"Результаты анализа: {test_name}")
    findings = []

    if any(x in text.lower() for x in ["density", "stress", "moisture", "shear"]):
        findings.append("✅ Найдены ключевые параметры.")
        st.success(findings[-1])
    else:
        findings.append("⚠ Внимание: Не найдены параметры. GPT поможет с анализом.")
        st.warning(findings[-1])

    return findings

def generate_pdf_report(test_name, findings):
    pdf = FPDF()
    pdf.add_page()

    font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
    pdf.add_font("DejaVu", "", font_path, uni=True)
    pdf.set_font("DejaVu", size=12)

    pdf.cell(200, 10, txt=f"Отчёт по тесту: {test_name}", ln=True)
    pdf.cell(200, 10, txt="", ln=True)
    for item in findings:
        pdf.multi_cell(0, 10, txt=str(item))  # безопасный вывод

    pdf_data = pdf.output(dest='S').encode("utf-8")
    return io.BytesIO(pdf_data)

# 🔥 GPT-анализ ASTM
def ask_gpt_astm_analysis(test_name, extracted_text):
    standard = astm_standards.get(test_name, "соответствующий ASTM стандарт")

    prompt = f"""
    Проанализируй текст протокола на соответствие стандарту **{standard}** для теста **{test_name}**.

    Укажи:
    1. Найденные параметры с числовыми значениями.
    2. Отсутствующие обязательные параметры.
    3. Оценку соответствия.
    4. Рекомендации по улучшению.

    Текст протокола:
    \"\"\"
    {extracted_text}
    \"\"\"
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Ошибка при обращении к GPT: {e}"

# ====== ИНТЕРФЕЙС STREAMLIT ======
st.set_page_config(page_title="Geotechnical Test Validator", layout="wide")
st.title("📊 Geotechnical Test Result Checker")
st.markdown("Загрузите PDF и выберите тип геотехнического теста для анализа согласно ASTM.")

test_types = list(astm_standards.keys())
tabs = st.tabs(test_types)

for i, test_name in enumerate(test_types):
    with tabs[i]:
        st.header(f"🧪 {test_name}")
        uploaded_file = st.file_uploader(f"Загрузите PDF для {test_name}", type="pdf", key=test_name)

        if uploaded_file:
            with st.spinner("Извлечение данных из PDF..."):
                text = extract_text_from_pdf(uploaded_file)
                st.success("✅ PDF успешно загружен и обработан.")

                findings = display_test_result(test_name, text)

                st.subheader("🤖 Анализ ChatGPT по ASTM")
                gpt_response = ask_gpt_astm_analysis(test_name, text)
                st.markdown(gpt_response)

                pdf_file = generate_pdf_report(test_name, findings)
                st.download_button(
                    label="📄 Скачать PDF отчёт",
                    data=pdf_file,
                    file_name=f"{test_name.replace(' ', '_')}_report.pdf",
                    mime="application/pdf"
                )
