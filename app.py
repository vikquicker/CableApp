import streamlit as st
import pandas as pd
import pulp
import numpy as np

# --- НАСТРОЙКА ЦВЕТОВОЙ СХЕМЫ (CSS) ---
st.set_page_config(page_title="Подбор кабеля", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
        /* Основной фон приложения (темно-графитовый) */
        .stApp {
            background-color: #14161A;
            color: #D1D5DB;
        }
        
        /* Закрашиваем пустое белое пространство снизу и убираем футер */
        body, html, [data-testid="stAppViewContainer"] {
            background-color: #14161A !important;
            min-height: 100vh;
        }
        footer {
            visibility: hidden;
        }
        
        /* Боковая панель */
        [data-testid="stSidebar"] {
            background-color: #1A1D24;
            border-right: 1px solid #2B2E38;
        }
        
        /* Отключаем прокрутку и скрываем кнопку сворачивания в боковой панели */
        [data-testid="stSidebar"] > div:first-child {
            overflow: hidden;
        }
        [data-testid="stSidebarCollapseButton"] {
            display: none;
        }
        [data-testid="collapsedControl"] {
            display: none;
        }
        
        /* Заголовки (Золотистый цвет) */
        h1, h2, h3 {
            color: #E8C55F !important;
            font-weight: 600;
            letter-spacing: 0.5px;
        }
        
        /* Текст и подписи */
        p, span, label {
            color: #D1D5DB !important;
        }
        
        /* Кнопки */
        .stButton > button {
            background-color: #242730;
            color: #E8C55F;
            border: 1px solid #3B3F4A;
            border-radius: 8px;
            padding: 0.5rem 1rem;
            transition: all 0.3s ease;
        }
        .stButton > button:hover {
            background-color: #2E323D;
            border-color: #E8C55F;
            color: #F4D03F;
        }
        
        /* Поля ввода (Number Inputs) */
        [data-testid="stNumberInput"] input {
            background-color: #1A1D24;
            color: #D1D5DB;
            border: 1px solid #3B3F4A;
            border-radius: 6px;
        }
        
        /* Таблица (Data Editor) */
        [data-testid="stDataFrame"] {
            background-color: #1A1D24;
            border: 1px solid #2B2E38;
            border-radius: 8px;
        }
        
        /* Блоки с результатами (Success/Error/Info) */
        .stAlert {
            border-radius: 8px;
        }
    </style>
    """,
    unsafe_allow_html=True
)
# ---------------------------------------

st.title("⚡ Умный подбор кабеля")

# Функция для красивого вывода чисел (убирает лишние нули, если число целое)
def format_num(val):
    if val is None or pd.isna(val): return ""
    val = float(val)
    if val.is_integer():
        return str(int(val))
    return f"{val:g}"

# --- ИНИЦИАЛИЗАЦИЯ СЕТКИ И ПЕРЕМЕННЫХ В ПАМЯТИ ---
if 'grid_data' not in st.session_state:
    cols = [f"Бухта {i+1}" for i in range(7)]
    st.session_state.grid_data = pd.DataFrame(
        np.nan, 
        index=range(5), 
        columns=cols
    )

if 'editor_version' not in st.session_state:
    st.session_state.editor_version = 0

if 'last_uploaded_file' not in st.session_state:
    st.session_state.last_uploaded_file = None

# --- БОКОВАЯ ПАНЕЛЬ (НАСТРОЙКИ) ---
st.sidebar.header("Параметры заказа")
target_length = st.sidebar.number_input("Требуемый метраж (м)", min_value=0.0, value=0.0, step=1.0, format="%g")

st.sidebar.header("Толеранс (допуск)")
pos_tol = st.sidebar.number_input("Положительный толеранс (%)", min_value=0, max_value=100, value=0, step=1, key="pos_tol_input") / 100.0
neg_tol = st.sidebar.number_input("Отрицательный толеранс (%)", min_value=0, max_value=100, value=0, step=1, key="neg_tol_input") / 100.0

st.sidebar.header("Правила маломеров")
mal_threshold = st.sidebar.number_input("Строительная длина", min_value=0.0, value=0.0, step=1.0, format="%g")
mal_pct = st.sidebar.number_input("Процент маломеров", min_value=0, max_value=100, value=0, step=1, key="mal_pct_input") / 100.0

st.sidebar.header("Правила короткомеров")
kor_threshold = st.sidebar.number_input("Порог короткомера", min_value=0.0, value=0.0, step=1.0, format="%g")
kor_pct = st.sidebar.number_input("Процент короткомеров", min_value=0, max_value=100, value=0, step=1, key="kor_pct_input") / 100.0

# --- ЗАГРУЗКА ФАЙЛА ---
uploaded_file = st.file_uploader("Внесите свои данные или загрузите Excel файл с упаковочным листом (заменит данные в таблице)", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:
    if uploaded_file != st.session_state.last_uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file, header=None)
            else:
                df = pd.read_excel(uploaded_file, header=None)
            
            header_row = -1
            header_col = -1
            
            for r_idx in range(len(df)):
                for c_idx in range(len(df.columns)):
                    val = str(df.iloc[r_idx, c_idx]).lower()
                    if "количество" in val:
                        header_row = r_idx
                        header_col = c_idx
                        break
                if header_row != -1:
                    break
                    
            if header_row != -1:
                max_row = len(df)
                for r_idx in range(header_row + 1, len(df)):
                    row_vals = df.iloc[r_idx, header_col:]
                    if row_vals.isna().all() or (row_vals.astype(str).str.strip() == '').all():
                        max_row = r_idx
                        break
                
                max_col = len(df.columns)
                for c_idx in range(header_col, len(df.columns)):
                    col_vals = df.iloc[header_row + 1 : max_row, c_idx]
                    if col_vals.isna().all() or (col_vals.astype(str).str.strip() == '').all():
                        max_col = c_idx
                        break
                
                extracted_df = df.iloc[header_row + 1 : max_row, header_col : max_col].copy()
                extracted_df = extracted_df.apply(pd.to_numeric, errors='coerce')
                extracted_df = extracted_df.dropna(how='all', axis=0).dropna(how='all', axis=1)
                
                if not extracted_df.empty:
                    extracted_df.columns = [f"Бухта {i+1}" for i in range(len(extracted_df.columns))]
                    extracted_df = extracted_df.reset_index(drop=True)
                    
                    st.session_state.grid_data = extracted_df
                    st.session_state.editor_version += 1
                    st.session_state.last_uploaded_file = uploaded_file
                    st.success("Данные из Excel успешно загружены в таблицу!")
                    st.rerun()
                else:
                    st.warning("В файле не найдено подходящих чисел под таблицей 'Количество'.")
                    st.session_state.last_uploaded_file = uploaded_file
            else:
                st.error("В файле не найдено слово 'Количество'. Убедитесь, что вы загрузили правильный упаковочный лист.")
                st.session_state.last_uploaded_file = uploaded_file
        except Exception as e:
            st.error(f"Ошибка при чтении файла: {e}")

# --- ИНТЕРФЕЙС ТАБЛИЦЫ ---
st.write("### Таблица метражей")
st.write("Впишите длины бухт вручную (только цифры).")

# Кнопки управления (выше таблицы)
c1, c2, c3 = st.columns([1, 1, 4])
with c1:
    if st.button("➕ Добавить строку"):
        new_row = pd.DataFrame(np.nan, index=[0], columns=st.session_state.grid_data.columns)
        st.session_state.grid_data = pd.concat([st.session_state.grid_data, new_row], ignore_index=True)
        st.session_state.editor_version += 1
        st.rerun()
with c2:
    if st.button("➖ Убрать строку"):
        if len(st.session_state.grid_data) > 1:
            st.session_state.grid_data = st.session_state.grid_data.iloc[:-1].reset_index(drop=True)
            st.session_state.editor_version += 1
            st.rerun()

# Настраиваем конфигурацию колонок (Запрет на буквы!)
col_config = {
    col: st.column_config.NumberColumn(col, format="%g") 
    for col in st.session_state.grid_data.columns
}

# Сама редактируемая сетка.
edited_df = st.data_editor(
    st.session_state.grid_data, 
    num_rows="fixed", 
    use_container_width=True,
    column_config=col_config,
    key=f"main_editor_{st.session_state.editor_version}"
)

# Сохраняем изменения из таблицы в память
st.session_state.grid_data = edited_df

# Собираем все числа из таблицы
lengths = []
for col in edited_df.columns:
    for val in edited_df[col]:
        if pd.notna(val) and float(val) > 0:
            lengths.append(float(val))

if not lengths:
    st.info("Введите данные в таблицу, чтобы начать расчет.")
else:
    # --- РЯД С КНОПКАМИ ДЕЙСТВИЙ ---
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    
    with col_btn1:
        btn_select = st.button("🚀 Подобрать бухты")
    with col_btn2:
        btn_check_mal = st.button("📏 Проверить маломеры")
    with col_btn3:
        btn_check_kor = st.button("📐 Проверить короткомеры")

    Total = sum(lengths)

    # --- РЕЖИМ 1: ПРОВЕРКА МАЛОМЕРОВ ---
    if btn_check_mal:
        mal_list = [l for l in lengths if l < mal_threshold]
        mal_total = sum(mal_list)
        limit = mal_pct * Total
        
        st.subheader("Результат проверки маломеров")
        st.write(f"**Общий метраж:** {format_num(Total)} м")
        st.write(f"**Метраж маломеров** (< {format_num(mal_threshold)} м): **{format_num(mal_total)}** м")
        st.write(f"**Разрешенный лимит** ({format_num(mal_pct*100)}%): **{format_num(limit)}** м")
        
        if mal_list:
            mal_str = ", ".join([format_num(x) for x in sorted(mal_list)])
            st.info(f"**Список маломеров (м):** {mal_str}")
        else:
            st.info("**Список маломеров (м):** отсутствуют")
        
        if mal_total <= limit:
            st.success("✅ Процент маломеров НЕ превышен. Склад в норме.")
        else:
            st.error(f"❌ Процент маломеров ПРЕВЫШЕН на {format_num(mal_total - limit)} м!")

    # --- РЕЖИМ 2: ПРОВЕРКА КОРОТКОМЕРОВ ---
    elif btn_check_kor:
        kor_list = [l for l in lengths if l < kor_threshold]
        kor_total = sum(kor_list)
        limit = kor_pct * Total
        
        st.subheader("Результат проверки короткомеров")
        st.write(f"**Общий метраж:** {format_num(Total)} м")
        st.write(f"**Метраж короткомеров** (< {format_num(kor_threshold)} м): **{format_num(kor_total)}** м")
        st.write(f"**Разрешенный лимит** ({format_num(kor_pct*100)}%): **{format_num(limit)}** м")
        
        if kor_list:
            kor_str = ", ".join([format_num(x) for x in sorted(kor_list)])
            st.info(f"**Список короткомеров (м):** {kor_str}")
        else:
            st.info("**Список короткомеров (м):** отсутствуют")
        
        if kor_total <= limit:
            st.success("✅ Процент короткомеров НЕ превышен. Склад в норме.")
        else:
            st.error(f"❌ Процент короткомеров ПРЕВЫШЕН на {format_num(kor_total - limit)} м!")

    # --- РЕЖИМ 3: ПОДБОР БУХТ ---
    elif btn_select:
        # Инициализируем переменные до расчетов, чтобы избежать ошибок вывода
        sel_sum = 0
        rem_sum = Total
        selected_lengths = []
        rem_lengths = lengths.copy()
        
        with st.spinner("Идет расчет..."):
            
            def solve_model(use_tolerance=True, use_limits=True):
                prob = pulp.LpProblem("Cable_Selection", pulp.LpMinimize)
                
                x = [pulp.LpVariable(f"x_{i}", cat='Binary') for i in range(len(lengths))]
                D_pos = pulp.LpVariable("D_pos", lowBound=0, cat='Continuous')
                D_neg = pulp.LpVariable("D_neg", lowBound=0, cat='Continuous')
                
                S = pulp.lpSum([x[i] * lengths[i] for i in range(len(lengths))])
                
                prob += D_pos + D_neg
                prob += S - target_length == D_pos - D_neg
                
                if use_tolerance:
                    prob += D_pos <= target_length * pos_tol
                    prob += D_neg <= target_length * neg_tol
                
                if use_limits:
                    Mal_Sel = pulp.lpSum([x[i] * lengths[i] for i in range(len(lengths)) if lengths[i] < mal_threshold])
                    Kor_Sel = pulp.lpSum([x[i] * lengths[i] for i in range(len(lengths)) if lengths[i] < kor_threshold])
                    Mal_Rem = pulp.lpSum([(1 - x[i]) * lengths[i] for i in range(len(lengths)) if lengths[i] < mal_threshold])
                    Kor_Rem = pulp.lpSum([(1 - x[i]) * lengths[i] for i in range(len(lengths)) if lengths[i] < kor_threshold])
                    
                    prob += Mal_Sel <= mal_pct * S
                    prob += Mal_Rem <= mal_pct * (Total - S)
                    prob += Kor_Sel <= kor_pct * S
                    prob += Kor_Rem <= kor_pct * (Total - S)
                
                # timeLimit=5 чтобы программа не зависала на нерешаемых задачах
                prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=5))
                return prob, x, S

            # 1. Пытаемся найти идеальный вариант со всеми ограничениями
            prob, x, S = solve_model(use_tolerance=True, use_limits=True)

            if pulp.LpStatus[prob.status] == 'Optimal':
                sel_sum = pulp.value(S)
                diff = sel_sum - target_length
                
                selected_indices = [i for i in range(len(lengths)) if pulp.value(x[i]) > 0.5]
                selected_lengths = [lengths[i] for i in selected_indices]
                rem_sum = Total - sel_sum
                rem_lengths = [lengths[i] for i in range(len(lengths)) if i not in selected_indices]
                
                st.subheader("Результаты подбора")
                
                if abs(diff) < 1e-5:
                    st.success("✅ Точный метраж найден!")
                else:
                    st.success("✅ Найден метраж с учётом толеранса!")
                    
            else:
                # 2. Если не удалось, запускаем диагностику: ищем без ограничений процентов
                prob_diag, x_diag, S_diag = solve_model(use_tolerance=True, use_limits=False)
                
                if pulp.LpStatus[prob_diag.status] == 'Optimal':
                    # Значит, метраж есть, но лимиты блокируют
                    st.error("❌ Не удается подобрать метраж с заданными процентами.")
                    st.warning("⚠️ **Важное пояснение:** Заданный метраж есть на складе, НО если его взять, то в остатке будет превышен лимит маломеров или короткомеров.")
                    st.info("Попробуйте увеличить процент маломеров/короткомеров или добавить положительный толеранс, чтобы захватить проблемные бухты в заказ.")
                    
                    # Показываем пользователю, ЧТО можно было бы взять без ограничений
                    sel_sum = pulp.value(S_diag)
                    selected_indices = [i for i in range(len(lengths)) if pulp.value(x_diag[i]) > 0.5]
                    selected_lengths = [lengths[i] for i in selected_indices]
                    rem_lengths = [lengths[i] for i in range(len(lengths)) if i not in selected_indices]
                    
                    st.write(f"*(Для справки) Без учета лимитов можно было бы взять:* {', '.join([format_num(l) for l in sorted(selected_lengths, reverse=True)])}")
                    
                else:
                    # Метраж невозможно собрать даже без ограничений
                    st.error("❌ Заданный метраж физически невозможно собрать из имеющихся бухт (даже без учета процентов).")
                    
                    # Показываем ближайший возможный вариант (максимально близкий к цели)
                    prob_fallback, x_fallback, S_fallback = solve_model(use_tolerance=False, use_limits=False)
                    if pulp.LpStatus[prob_fallback.status] == 'Optimal':
                        st.info("Показываем ближайший возможный вариант из имеющихся бухт:")
                        sel_sum = pulp.value(S_fallback)
                        selected_indices = [i for i in range(len(lengths)) if pulp.value(x_fallback[i]) > 0.5]
                        selected_lengths = [lengths[i] for i in selected_indices]
                        rem_lengths = [lengths[i] for i in range(len(lengths)) if i not in selected_indices]
                        st.subheader("Ближайший возможный вариант")
                    else:
                        st.error("Не удалось подобрать ни один вариант.")
                        selected_lengths = []

            # Вывод метрик и списков, если они найдены
            if 'selected_lengths' in locals() and selected_lengths:
                col1, col2, col3 = st.columns(3)
                col1.metric("Подобранный метраж", f"{format_num(sel_sum)} м", f"{format_num(sel_sum - target_length)} м от цели")
                col2.metric("Остаток", f"{format_num(Total - sel_sum)} м")
                col3.metric("Бухт выбрано", len(selected_lengths))
                
                st.write("**Выбранные бухты:**", ", ".join([format_num(l) for l in sorted(selected_lengths, reverse=True)]))
                st.write("**Оставшиеся бухты:**", ", ".join([format_num(l) for l in sorted(rem_lengths, reverse=True)]))
