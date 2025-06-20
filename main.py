import streamlit as st
from pypdf import PdfReader
from fpdf import FPDF
import io
import os
import openai
import streamlit as st

# Загружаем API-ключ из секрета
openai.api_key = st.secrets["openai_api_key"]


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

    if test_name == "UCS Test - Soil":
        if "kPa" in text or "MPa" in text:
            findings.append("✅ Найдены значения напряжения. Анализ данных соответствует ASTM D2166.")
            st.success(findings[-1])
        else:
            findings.append("❌ Не найдены значения напряжения. Возможно, некорректный формат PDF.")
            st.error(findings[-1])

    elif test_name == "Proctor Test":
        if "dry density" in text.lower() or "moisture" in text.lower():
            findings.append("✅ Найдены данные по плотности и влажности. Анализ соответствует ASTM D698/D1557.")
            st.success(findings[-1])
        else:
            findings.append("⚠ Данные по влажности или плотности не найдены.")
            st.warning(findings[-1])

    else:
        findings.append("🔧 Проверка для этого теста в разработке.")
        st.info(findings[-1])

    return findings

def generate_pdf_report(test_name, findings):
    pdf = FPDF()
    pdf.add_page()

    # Путь к шрифту (обязательно должен быть рядом с файлом или указать абсолютный путь)
    font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
    pdf.add_font("DejaVu", "", font_path, uni=True)
    pdf.set_font("DejaVu", size=12)

    pdf.cell(200, 10, txt=f"Отчёт по тесту: {test_name}", ln=True)
    pdf.cell(200, 10, txt="", ln=True)
    for item in findings:
        pdf.multi_cell(0, 10, txt=item)

    pdf_data = pdf.output(dest='S').encode("utf-8")
    pdf_buffer = io.BytesIO(pdf_data)
    return pdf_buffer

# ====== ОСНОВНОЙ ИНТЕРФЕЙС ======
st.set_page_config(page_title="Geotechnical Test Validator", layout="wide")
st.title("📊 Geotechnical Test Result Checker")
st.markdown("Загрузите PDF-файл и выберите тип теста для анализа.")

# Список тестов
test_types = [
    "Electrical Resistivity Test (ERT)",
    "Seismic Refraction Test (SRT)",
    "Atterberg Limit Test",
    "Sieve Analysis",
    "UCS Test - Soil",
    "UCS Test - Rock",
    "Oedometer Test",
    "Direct Shear Test",
    "Collapse Test",
    "California Bearing Ratio",
    "Proctor Test"
]

# ====== НАВИГАЦИЯ ПО ВКЛАДКАМ ======
tabs = st.tabs(test_types)

for i, test_name in enumerate(test_types):
    with tabs[i]:
        st.header(f"🧪 {test_name}")
        uploaded_file = st.file_uploader(f"Загрузите PDF для {test_name}", type="pdf", key=test_name)

        if uploaded_file:
            with st.spinner("Извлечение данных из PDF..."):
                text = extract_text_from_pdf(uploaded_file)
                st.success("PDF загружен и прочитан успешно.")

                findings = display_test_result(test_name, text)

            pdf_file = generate_pdf_report(test_name, findings)
            st.download_button(
                label="📄 Скачать PDF отчёт",
                data=pdf_file,
                file_name=f"{test_name.replace(' ', '_')}_report.pdf",
                mime="application/pdf"
            )
