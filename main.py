import streamlit as st
from pypdf import PdfReader
import pandas as pd
import math
import re
from openai import OpenAI
from io import BytesIO

# --- API ---
client = OpenAI(api_key=st.secrets["openai_api_key"])

# --- Конфигурации ---
column_translations = {
    "ru": ["№ п/п", "№ Выработки", "Расстояние между электродами а, (м)", "Показание прибора R, (Ом)",
           "Удельное электрическое сопротивление ρ=2πRa Ом·м", "Коррозионная агрессивность по NACE",
           "Коррозионная активность по ASTM"],
    "en": ["No.", "Test Point", "Electrode Spacing a, (m)", "Instrument Reading R (Ohm)",
           "Resistivity ρ = 2πRa (Ohm·m)", "Corrosion Class (NACE)", "Corrosion Activity (ASTM)"],
    "uz": ["№", "Ish joyi", "Elektrodlar orasidagi masofa a, (m)", "Asbob ko'rsatkichi R (Om)",
           "Xususiy qarshilik ρ = 2πRa (Om·m)", "Korroziya klassi (NACE)", "Korroziya faolligi (ASTM)"]
}

corrosion_labels = {
    "ru": {
        "Низкое": "Низкое", "Слабо коррозионный": "Слабо коррозионный", "Умеренно коррозионный": "Умеренно коррозионный",
        "Коррозионно-активный": "Коррозионно-активный", "Высококоррозионный": "Высококоррозионный",
        "Очень слабая коррозия": "Очень слабая коррозия", "Чрезвычайно коррозионный": "Чрезвычайно коррозионный",
        "Out of range": "Вне диапазона", "Invalid": "Недействительно"
    },
    "en": {
        "Низкое": "Low", "Слабо коррозионный": "Slightly Corrosive", "Умеренно коррозионный": "Moderately Corrosive",
        "Коррозионно-активный": "Corrosive", "Высококоррозионный": "Highly Corrosive",
        "Очень слабая коррозия": "Very Low", "Чрезвычайно коррозионный": "Severe",
        "Out of range": "Out of range", "Invalid": "Invalid"
    },
    "uz": {
        "Низкое": "Past", "Слабо коррозионный": "Yengil korroziv", "Умеренно коррозионный": "O'rtacha korroziv",
        "Коррозионно-активный": "Faol korroziv", "Высококоррозионный": "Yuqori korroziv",
        "Очень слабая коррозия": "Juda past", "Чрезвычайно коррозионный": "Juda kuchli",
        "Out of range": "Tashqarida", "Invalid": "Noto‘g‘ri"
    }
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
    "Низкое": "#d0f0c0", "Очень слабая коррозия": "#d0f0c0",
    "Слабо коррозионный": "#fef3bd", "Умеренно коррозионный": "#ffd59e",
    "Коррозионно-активный": "#ffadad", "Высококоррозионный": "#ff6b6b",
    "Чрезвычайно коррозионный": "#ff6b6b", "Out of range": "#cccccc", "Invalid": "#e0e0e0"
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

# --- Утилиты ---
def extract_text_from_pdf(pdf_file):
    reader = PdfReader(pdf_file)
    return "".join([page.extract_text() or "" for page in reader.pages])

def format_float(val):
    try:
        return f"{round(float(str(val).replace(',', '.')), 2):.2f}"
    except:
        return "-"

def parse_distance_to_meters(raw_value):
    val = raw_value.lower().strip().replace(",", ".")
    if "см" in val or "cm" in val:
        numbers = re.findall(r"[\d.]+", val)
        if numbers:
            return round(float(numbers[0]) / 100, 4)
    try:
        fval = float(val)
        return round(fval / 100, 4) if fval > 10 else round(fval, 4)
    except:
        return None

def classify_corrosion(resistivity_ohm_m):
    try:
        val = float(resistivity_ohm_m)
        for low, high, nace, astm in corrosion_classes:
            if low <= val <= high:
                return nace, astm
        return "Out of range", "Out of range"
    except:
        return "Invalid", "Invalid"

def ask_gpt_astm_analysis(test_name, extracted_text, model_name, language_code):
    standard = astm_standards.get(test_name, "соответствующий ASTM стандарт")
    prompt = f'''
From the report below for the "{test_name}" test:

1. Extract ALL ERT rows.
2. Create a table:
- № п/п | № Выработки | Расстояние между электродами, а (м) | Показание прибора R (Ом) | Удельное сопротивление ρ = 2πRa (Ом·м) | Коррозионная агрессивность по NACE | Коррозионная активность по ASTM
3. Round numbers to 2 decimals. Write "-" if missing.
4. After the table: list all missing values and auto-calculated ones.

Language: {language_code.upper()}
"""
{extracted_text}
"""
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

def gpt_response_to_table(response, lang_code):
    lines = [line for line in response.splitlines() if "|" in line and "№" not in line and "---" not in line]
    data = []
    for line in lines:
        parts = [p.strip() for p in line.strip("- ").split("|") if p.strip()]
        if len(parts) < 5:
            continue
        number, well_no, a_raw, r_val, rho_val = parts[:5]
        a_m = parse_distance_to_meters(a_raw)
        a_val = format_float(a_m) if a_m else "-"
        try: r_float = float(r_val.replace(",", ".")) if r_val != "-" else None
        except: r_float = None
        try: rho_float = float(rho_val.replace(",", ".")) if rho_val != "-" else None
        except: rho_float = None
        if (rho_float is None or rho_float < 20) and r_float and a_m:
            rho_val = format_float(2 * math.pi * r_float * a_m)
        else:
            rho_val = format_float(rho_float)
        nace, astm = classify_corrosion(rho_val)
        nace = corrosion_labels[lang_code].get(nace, nace)
        astm = corrosion_labels[lang_code].get(astm, astm)
        data.append([number, well_no, a_val, format_float(r_val), rho_val, nace, astm])
    return pd.DataFrame(data, columns=column_translations[lang_code])

def style_table(df):
    def color(val): return f"background-color: {corrosion_colors.get(val, '')}"
    def highlight(val): return "background-color: #fdd" if val in ["-", "nan", "", None] else ""
    return df.style.applymap(color, subset=[df.columns[-2], df.columns[-1]]).applymap(highlight)

missing_explanations = {
    "ru": {
        "R": "отсутствует значение R (показание прибора)",
        "ρ": "отсутствует значение удельного сопротивления, программа рассчитала автоматически"
    },
    "en": {
        "R": "missing value of R (instrument reading)",
        "ρ": "missing resistivity value, calculated automatically by the program"
    }
}

def explain_missing_values(df, lang_code):
    messages = []
    for idx, row in df.iterrows():
        well = row[1]
        r = str(row[3]).strip().lower()
        rho = str(row[4]).strip().lower()
        if r in ["-", "", "nan", "none"]:
            messages.append(f"{well} – {missing_explanations[lang_code]['R']}")
        if rho in ["-", "", "nan", "none"]:
            messages.append(f"{well} – {missing_explanations[lang_code]['ρ']}")
    return messages

# --- Интерфейс ---
st.set_page_config("Geotechnical Test Checker", layout="wide")
st.title("Geotechnical Test Validator")

lang = st.sidebar.selectbox("🌐 Language:", ["Русский", "English", "O'zbek"])
lang_codes = {"Русский": "ru", "English": "en", "O'zbek": "uz"}
language_code = lang_codes[lang]

model_choice = st.sidebar.selectbox(" Juru AI Model:", ["gpt-4-turbo", "gpt-3.5-turbo"])

st.markdown("Upload a PDF report and select a test type to validate against ASTM.")

test_types = list(astm_standards.keys())
tabs = st.tabs(test_types)

for i, test_name in enumerate(test_types):
    with tabs[i]:
        st.header(test_name)
        uploaded_file = st.file_uploader(f"📎 Upload PDF for {test_name}", type="pdf", key=test_name)

       if uploaded_file:
    with st.spinner("Reading PDF..."):
        text = extract_text_from_pdf(uploaded_file)
        st.success("✅ PDF loaded.")

    gpt_response = ask_gpt_astm_analysis(test_name, text, model_choice, language_code)
    df_result = gpt_response_to_table(gpt_response, language_code)
    st.dataframe(style_table(df_result), use_container_width=True)

    # 🔍 Пояснения по пропущенным значениям
    missing_notes = explain_missing_values(df_result, language_code)
    if missing_notes:
        st.subheader("📌 Дополнительные замечания:")
        for note in missing_notes:
            st.markdown(f"- {note}")

    # ❗ Явный вывод по отсутствию значений
    missing = []
    for row in df_result.itertuples(index=False):
        for i, val in enumerate(row):
            if str(val).strip().lower() in ["-", "nan", "", "none"]:
                missing.append(f"❌ Пропущено в строке {getattr(row, df_result.columns[0])}, колонка '{df_result.columns[i]}'")

    if missing:
        st.subheader("⚠️ Missing values:")
        for m in missing:
            st.markdown(f"- {m}")
    else:
        st.success("✅ All values present.")

    # 💬 Комментарии GPT
    comments = [l for l in gpt_response.splitlines() if "|" not in l and "---" not in l and l.strip()]
    if comments:
        st.subheader("Juru AI Comments:")
        for c in comments:
            st.markdown(f"- {c}")

    # 📥 Excel
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
        df_result.to_excel(writer, index=False, sheet_name="GPT Analysis")
    st.download_button("📥 Download Excel", data=excel_buffer.getvalue(), file_name=f"{test_name}.xlsx")
