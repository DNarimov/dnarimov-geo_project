import streamlit as st
from pypdf import PdfReader
import pandas as pd
import math
import re
from openai import OpenAI
from io import BytesIO

client = OpenAI(api_key=st.secrets["openai_api_key"])

column_translations = {
    "ru": ["№ п/п", "№ Выработки", "Расстояние между электродами а, (м)", "Показание прибора R, (Ом)",
            "Удельное электрическое сопротивление ρ=2πRa Ом·м", "Коррозионная агрессивность по NACE",
            "Коррозионная активность по ASTM"],
    "en": ["No.", "Test Point", "Electrode Spacing a, (m)", "Instrument Reading R (Ohm)",
            "Resistivity ρ = 2πRa (Ohm·m)", "Corrosion Class (NACE)", "Corrosion Activity (ASTM)"],
    "uz": ["№", "Ish joyi", "Elektrodlar orasidagi masofa a, (m)", "Asbob ko'rsatkichi R (Om)",
            "Xususiy qarshilik ρ = 2πRa (Om·m)", "Korroziya klassi (NACE)", "Korroziya faolligi (ASTM)"]
}

corrosion_labels = { ... }  # Вставьте словарь с переводами из предыдущего сообщения

astm_standards = { ... }  # как раньше

corrosion_classes = [ ... ]  # как раньше

corrosion_colors = { ... }  # как раньше

def classify_corrosion(val):
    try:
        v = float(val)
        for low, high, nace, astm in corrosion_classes:
            if low <= v <= high:
                return nace, astm
        return "Out of range", "Out of range"
    except:
        return "Invalid", "Invalid"

def format_float(val):
    try:
        return f"{round(float(str(val).replace(',', '.')), 2):.2f}"
    except:
        return "-"

def parse_distance_to_meters(raw):
    val = raw.lower().strip().replace(",", ".")
    if "см" in val or "cm" in val:
        digits = re.findall(r"[\d.]+", val)
        return round(float(digits[0]) / 100, 4) if digits else None
    try:
        f = float(val)
        return round(f / 100, 4) if f > 10 else round(f, 4)
    except:
        return None

def extract_text_from_pdf(pdf_file):
    reader = PdfReader(pdf_file)
    return "".join([p.extract_text() or "" for p in reader.pages])

def ask_gpt_astm_analysis(test_name, text, model, lang):
    prompt = f'''
From the report below for the "{test_name}" test, perform:
- Extract ALL tabular data rows
- Format: columns for #:, point, a (m), R, resistivity, NACE, ASTM
- Use 2 decimal places
- Show '-' for missing values
- After table, write a plain summary:
  * which values were missing and calculated
  * what ASTM fields are missing
  * conclusion about compliance
Use language: {lang.upper()}

"""
{text}
"""
'''
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=2000
    )
    return resp.choices[0].message.content

def gpt_response_to_table(resp, lang):
    lines = [l for l in resp.strip().split("\n") if l.strip() and "|" in l and "---" not in l and "№" not in l]
    data = []
    for l in lines:
        parts = [p.strip() for p in l.strip("- ").split("|") if p.strip()]
        if len(parts) < 5:
            continue
        num, point, a_raw, r_val, rho_val = parts[:5]
        a = parse_distance_to_meters(a_raw)
        r = format_float(r_val)
        rho = format_float(2 * math.pi * float(r) * a) if (a and r != '-') else format_float(rho_val)
        nace, astm = classify_corrosion(rho)
        t_nace = corrosion_labels[lang].get(nace, nace)
        t_astm = corrosion_labels[lang].get(astm, astm)
        data.append([num, point, format_float(a), r, rho, t_nace, t_astm])
    return pd.DataFrame(data, columns=column_translations[lang])

def style_table(df):
    def style_corrosion(v): return f"background-color: {corrosion_colors.get(v, '#fff')}"
    return df.style \
        .applymap(style_corrosion, subset=df.columns[-2:])

# === Streamlit UI ===
st.set_page_config("Geotechnical Test Result Checker", layout="wide")
st.title("Geotechnical Test Result Checker")

lang = st.sidebar.selectbox("🌐 Language / Язык", ["Русский", "English", "O'zbek"])
lang_code = {"Русский": "ru", "English": "en", "O'zbek": "uz"}[lang]

model_choice = st.sidebar.selectbox("🤖 Juru AI Model", ["gpt-4-turbo", "gpt-3.5-turbo"])

tests = list(astm_standards.keys())
tabs = st.tabs(tests)

for i, test in enumerate(tests):
    with tabs[i]:
        st.subheader(test)
        file = st.file_uploader(f"Upload PDF for {test}", type="pdf", key=test)
        if file:
            text = extract_text_from_pdf(file)
            with st.spinner("Analyzing..."):
                response = ask_gpt_astm_analysis(test, text, model_choice, lang_code)
                df = gpt_response_to_table(response, lang_code)
            st.dataframe(style_table(df), use_container_width=True)

            # Summary
            st.markdown("### Summary & Compliance")
            summary_started = False
            for line in response.splitlines():
                if any(word in line.lower() for word in ["summary", "итог", "соответствие", "compliance"]):
                    summary_started = True
                if summary_started and line.strip() and "|" not in line:
                    st.markdown(f"- {line.strip('-•* ')}")

            # Download
            out = BytesIO()
            with pd.ExcelWriter(out, engine="xlsxwriter") as w:
                df.to_excel(w, index=False)
            st.download_button("📄 Скачать Excel", out.getvalue(), file_name="ERT_Report.xlsx")
