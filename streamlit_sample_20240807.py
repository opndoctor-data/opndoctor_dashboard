import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import matplotlib.pyplot as plt
import urllib.parse
import datetime
from geopy.distance import distance
import plotly.graph_objs as go
import re

# 오늘 날짜를 YYYYMM으로 변환
# 그 전달로 설정
this_date = datetime.datetime.now() - datetime.timedelta(days=30)
this_date = this_date.strftime('%Y%m')

st.title("오픈닥터 대시보드")
st.markdown(
    """
    <p style='font-size: 12px; color: gray;'> 최신 매출 년월: {}년 {}월</p>
    """.format(this_date[:4], this_date[4:]), 
    unsafe_allow_html=True
    )

def get_engine():
    user = 'postgres'
    password = 'welcome2od!'
    host = 'opn-db-ci-test.crwmcix5qrfg.ap-northeast-2.rds.amazonaws.com'
    port = '5432'
    database = 'postgres'
    connection_string = f'postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}'
    return create_engine(connection_string)

@st.cache_data(ttl=3600)
def load_hospital_sales():
    query = """
    SELECT 코드, mct_brn, ta_ym, est_hga, est_cnt
    FROM db_prog.hospital_sales hs
    WHERE est_hga != 0
    """
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

@st.cache_data(ttl=3600)
def load_hospitals(this_date):
    query = """
    SELECT *
    FROM db_prog.hospitals h
    WHERE update_ta_ym = '{}'
    AND 지번주소 IS NOT NULL
    AND 오픈닥터_진료과 IS NOT NULL
    """.format(this_date)
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

@st.cache_data(ttl=3600)
def load_dongs():
    query = """
    SELECT * FROM db_prog.bjdongs
    WHERE 읍면동명 IS NOT NULL
    """
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

def initialize_session_state():
    if 'selected_location' not in st.session_state:
        st.session_state.selected_location = ['전체']
    if 'selected_department' not in st.session_state:
        st.session_state.selected_department = ['전체']
    if 'selected_range' not in st.session_state:
        st.session_state.selected_range = (0, 10000000000)
    if 'selected_ym' not in st.session_state:
        st.session_state.selected_ym = (202001, 202406)
    if 'selected_hospital_name' not in st.session_state:
        st.session_state.selected_hospital_name = None
    if 'selected_hospital_address' not in st.session_state:
        st.session_state.selected_hospital_address = None
    if 'selected_code' not in st.session_state:
        st.session_state.selected_code = None
    if 'filtered_hospitals' not in st.session_state:
        st.session_state.filtered_hospitals = None
    if 'filtered_sales' not in st.session_state:
        st.session_state.filtered_sales = None
    if 'sales_within_radius' not in st.session_state:
        st.session_state.sales_within_radius = None
    if 'hospitals_within_radius' not in st.session_state:
        st.session_state.hospitals_within_radius = None
    if 'selected_radius_code' not in st.session_state:
        st.session_state.selected_radius_code = None

def load_filtered_data(selected_location, selected_department):
    initial_hospitals = st.session_state['initial_hospitals']
    # 주소로 필터링
    # selected_location은 리스트 형식
    # 리스트 안에 있는 텍스트들을 모두 충족하는 데이터만 필터링
    filtered_hospitals = pd.DataFrame()
    for loc in selected_location:
        if len(selected_location) == 1 and loc == '전체':
            filtered_hospitals = pd.concat([filtered_hospitals, initial_hospitals])
        else:
            filtered_hospitals = pd.concat([filtered_hospitals, initial_hospitals[initial_hospitals['지번주소'].str.contains(loc)]])
    # 진료과목도 위처럼 동일하게
    filtered_hospitals_final = pd.DataFrame()
    for dep in selected_department:
        if len(selected_department) == 1 and dep == '전체':
            filtered_hospitals_final = pd.concat([filtered_hospitals_final, filtered_hospitals])
        elif dep == '외과':
            filtered_hospitals_final = pd.concat([filtered_hospitals_final, filtered_hospitals[(filtered_hospitals['오픈닥터_진료과'].str.startswith('외과')) | (filtered_hospitals['오픈닥터_진료과'].str.contains(', 외과'))]])
        else:
            filtered_hospitals_final = pd.concat([filtered_hospitals_final, filtered_hospitals[filtered_hospitals['오픈닥터_진료과'].str.contains(dep)]])
    
    return filtered_hospitals_final

def render_sidebar_filters(initial_hospitals, dong_data):
    col1, col2 = st.sidebar.columns([0.68, 0.38])
    with col2:
        reset_button = st.button('초기화', key='filter_reset')
    if reset_button:
        st.session_state.selected_location = ['전체']
        st.session_state.selected_department = ['전체']
        st.session_state.selected_range = (0, 10000000000)
        st.session_state.selected_ym = (202001, 202407)
        st.session_state.selected_code = None
        st.session_state.selected_hospital_name = None
        st.session_state.selected_hospital_address = None
        st.session_state.filtered_hospitals = None
        st.session_state.filtered_sales = None
    
    st.sidebar.header('필터')
    st.sidebar.write("지역 정보")
    # 주의 사항 아주 작게 표기
    st.sidebar.markdown(
    """
    <p style='font-size: 12px; color: gray;'> 원활한 검색을 위해 시도 단위 정도는 꼭 입력해주세요.</p>
    """, 
    unsafe_allow_html=True
    )
    
    unique_sido = ['전체'] + sorted(dong_data['시도명'].dropna().unique())
    selected_sido = st.sidebar.selectbox('시도', unique_sido, key='filter_selected_sido')

    unique_sigungu = ['전체']
    if selected_sido != '전체':
        unique_sigungu += sorted(dong_data[dong_data['시도명'] == selected_sido]['시군구명'].dropna().unique())
    selected_sigungu = st.sidebar.selectbox('시군구', unique_sigungu, key='filter_selected_sigungu')

    unique_eupmyeondong = ['전체']
    if selected_sigungu != '전체':
        unique_eupmyeondong += sorted(dong_data[(dong_data['시도명'] == selected_sido) & (dong_data['시군구명'] == selected_sigungu)]['읍면동명'].dropna().unique())
    selected_eupmyeondong = st.sidebar.selectbox('읍면동', unique_eupmyeondong, key='filter_selected_eupmyeondong')

    # 위의 조합으로 법정동 주소 우선 만들어놓기
    selected_location = ' '.join(filter(lambda x: x != '전체', [selected_sido, selected_sigungu, selected_eupmyeondong]))
    if selected_location == '':
        selected_location = '전체'

    # 지역 추가 버튼
    add_button_location = st.sidebar.button("추가", key='add_button_location')
    # 추가 버튼을 누르면, 선택한 필터들을 session_state에 저장
    if add_button_location:
        if "전체" in st.session_state.selected_location:
            st.session_state.selected_location = []
        st.session_state.selected_location.append(selected_location)
    
    # 선택한 필터들을 보여주기
    st.sidebar.write("현재 선택한 지역", bold=True)
    if "전체" not in st.session_state.selected_location:
        # 박스 안에 리스트로 보여주기
        # 박스 배경은 검은색, 글자는 흰색
        location_info_box = """
        <div style="background-color:#0E1117; padding:10px; border-radius:10px;">
        <p style='font-size: 14px; color: white;'> {}</p>
        """.format(", ".join(st.session_state.selected_location))
        st.sidebar.markdown(location_info_box, unsafe_allow_html=True)

    st.sidebar.markdown("<hr>", unsafe_allow_html=True)
    
    # 진료과목 리스트로 뽑기
    initial_hospitals = initial_hospitals[initial_hospitals['오픈닥터_진료과'].notnull()]
    hos_type_list = initial_hospitals[~initial_hospitals['오픈닥터_진료과'].str.contains(",")]['오픈닥터_진료과'].unique().tolist()
    unique_department = ['전체'] + sorted(hos_type_list)
    selected_department = st.sidebar.selectbox('진료과', unique_department, key='filter_selected_department')

    # 진료과목 추가 버튼
    add_button_department = st.sidebar.button("추가", key='add_button_department')
    # 추가 버튼을 누르면, 선택한 필터들을 session_state에 저장
    if add_button_department:
        if "전체" in st.session_state.selected_department:
            st.session_state.selected_department = []
        st.session_state.selected_department.append(selected_department)
    
    # 선택한 필터들을 보여주기
    st.sidebar.write("현재 선택한 진료과목")
    if "전체" not in st.session_state.selected_department:
        department_info_box = """
        <div style="background-color:#0E1117; padding:10px; border-radius:10px;">
        <p style='font-size: 14px; color: white;'> {}</p>
        </div>
        """.format(", ".join(st.session_state.selected_department))
        st.sidebar.markdown(department_info_box, unsafe_allow_html=True)

    st.sidebar.markdown("<hr>", unsafe_allow_html=True)

    # 매출 범위 선택
    st.sidebar.write("매출 정보")
    st.sidebar.markdown(
    """
    <p style='font-size: 12px; color: gray;'> 매출에 대한 상세 범위를 설정해주세요.</p>
    """, 
    unsafe_allow_html=True
    )
    
    st.sidebar.write("시작 년월")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        min_year = st.number_input("년", min_value=2020, max_value=2024, value=2020, key='min_year')
    with col2:
        min_month = st.number_input("월", min_value=1, max_value=12, value=1, key='min_month')

    st.sidebar.write("종료 년월")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        max_year = st.number_input("년", min_value=2020, max_value=2024, value=2024, key='max_year')
    with col2:
        max_month = st.number_input("월", min_value=1, max_value=12, value=7, key='max_month')
    
    st.sidebar.markdown("<br>", unsafe_allow_html=True)

    # 최소값 입력 박스를 한 줄에 배치
    # 최소매출 글자는 헤더보다 조금 작게 표시
    st.sidebar.write("최소 매출")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        min_value = st.number_input("억", min_value=0, max_value=10000, value=0, key='min_value')
    with col2:
        min_subvalue = st.number_input("만원", min_value=0, max_value=9999, value=0, step=100, key='min_subvalue')

    # 최대값 입력 박스를 한 줄에 배치
    st.sidebar.write("최대 매출")
    col3, col4 = st.sidebar.columns(2)
    with col3:
        max_value = st.number_input("억", min_value=0, max_value=10000, value=1000, key='max_value')
    with col4:
        max_subvalue = st.number_input("만원", min_value=0, max_value=9999, value=0, step=100, key='max_subvalue')

    # 입력값을 정수로 변환
    def combine_values(value, subvalue):
        return value * 100000000 + subvalue * 10000
    
    def combine_ym(year, month):
        if month < 10:
            return f"{year}0{month}"
        else:
            return f"{year}{month}"

    # 최소값과 최대값 합치기
    min_combined_value = combine_values(min_value, min_subvalue)
    max_combined_value = combine_values(max_value, max_subvalue)
    selected_range = (min_combined_value, max_combined_value)

    # 최소년월과 최대년월 합치기
    min_ym = combine_ym(min_year, min_month)
    max_ym = combine_ym(max_year, max_month)
    selected_ym = (min_ym, max_ym)

    st.sidebar.markdown("<br>", unsafe_allow_html=True)

    # 결과 출력
    if min_value == 0:
        st.sidebar.write("최소 매출: {}만원".format(min_subvalue))
    elif min_subvalue == 0:
        st.sidebar.write(f"최소 매출: {min_value}억원")
    else:
        st.sidebar.write(f"최소 매출: {min_value}억 {min_subvalue}만원")
    
    if max_value == 0:
        st.sidebar.write("최대 매출: {}만원".format(max_subvalue))
    elif max_subvalue == 0:
        st.sidebar.write(f"최대 매출: {max_value}억원")
    else:
        st.sidebar.write(f"최대 매출: {max_value}억 {max_subvalue}만원")

    # 유효한 입력값인지 확인
    if min_combined_value > max_combined_value:
        st.sidebar.write("최소 매출 값이 최대 매출 값보다 클 수 없습니다.")

    apply_button = st.sidebar.button('적용', key='filter_apply')
    if apply_button:
        st.session_state.filtered_hospitals = load_filtered_data(st.session_state.selected_location, st.session_state.selected_department)
        st.session_state.selected_code = None
        st.session_state.selected_hospital_name = None
        st.session_state.selected_hospital_address = None
        st.session_state.filtered_sales = None
        st.session_state.selected_range = selected_range
        st.session_state.selected_ym = selected_ym

def render_filtered_data_hosname(filtered_data):
    st.sidebar.markdown("<hr>", unsafe_allow_html=True)
    st.sidebar.subheader("병원명 선택")
    st.sidebar.markdown(
    """
    <p style='font-size: 12px; color: gray;'> 위에서 필터를 많이 걸어놓을수록 조회가 빠릅니다.</p>
    """, 
    unsafe_allow_html=True
    )
    unique_hospital_names = filtered_data['의원명'].unique()
    selected_hospital_name = st.sidebar.selectbox(
        "병원을 선택하세요:",
        unique_hospital_names, 
        key='filter_hospital_name'
    )
    st.sidebar.write(f"병원 이름: {selected_hospital_name}")
    return selected_hospital_name

def render_filtered_data_hosaddress(filtered_data, selected_hospital_name):
    st.sidebar.subheader("주소 선택")
    selected_hospital_address = st.sidebar.selectbox(
        "주소를 선택하세요:",
        filtered_data[filtered_data['의원명'] == selected_hospital_name]['정제주소'].unique(),
        index=0,
        key='filter_hospital_address'
    )
    st.sidebar.write(f"병원 주소: {selected_hospital_address}")
    return selected_hospital_address

def render_table(filtered_df, selected_code, filtered_sales):
    col1, col2 = st.columns([0.4, 0.6])
    with col1:
        st.write("매출 현황")
        filtered_df = filtered_df[['ta_ym', 'est_hga', 'est_cnt']]
        if len(filtered_df) > 0:
            # 테이블 제목 먼저 출력
            filtered_df['est_hga'] = filtered_df['est_hga'].map('{:,.0f}'.format)
            filtered_df['est_cnt'] = filtered_df['est_cnt'].map('{:,.0f}'.format)
            # 인덱스 컬럼 삭제
            filtered_df = filtered_df.reset_index(drop=True)
            filtered_df.rename(columns={'ta_ym': '매출년월', 'est_hga': '매출액', 'est_cnt': '결제건수'}, inplace=True)
            st.dataframe(filtered_df.style.set_properties(**{
                'background-color': 'white',
                'color': 'black',
                'border-color': 'black',
                'font-size': '14px',
            }), hide_index=True)
        else:
            filtered_df = pd.DataFrame(columns=['매출년월', '매출액', '결제건수'])
            st.dataframe(filtered_df.style.set_properties(**{
                'background-color': 'white',
                'color': 'black',
                'border-color': 'black',
                'font-size': '14px',
            }), hide_index=True)
    with col2:
        st.write("병원 정보")
        hospital_info = st.session_state.filtered_hospitals[st.session_state.filtered_hospitals['코드'] == selected_code]
        hospital_info['전문의현황'] = hospital_info['전문의현황'].fillna("")
        hospital_info['전문의'] = hospital_info['전문의'].fillna(0)
        hospital_info['일반의'] = hospital_info['일반의'].fillna(0)
        hospital_info['의료장비정보'] = hospital_info['의료장비정보'].fillna("")
        special_doctors = hospital_info['전문의현황'].to_list()[0]
        special_doctors = re.sub(r'\S+ 0명(, )?', '', special_doctors).strip(", ")
        hospital_info['전문의현황'] = special_doctors
        if hospital_info['전문의'].to_list()[0] == 0:
            st.markdown(
                    f"""
                    <div style='padding: 20px; border: 1px solid #ddd; border-radius: 10px; background-color: #f9f9f9;'>
                        <h2 style='color: black;'>{hospital_info['의원명'].to_list()[0]}</h2>
                        <ul style='list-style-type: disc; padding-left: 10px; color: black;'>
                            <li>주소: {hospital_info['주소'].to_list()[0]}</li>
                            <li>진료과목: {hospital_info['오픈닥터_진료과'].to_list()[0]}</li>
                            <li>개원일자: {hospital_info['개설일자'].to_list()[0]}</li>
                            <li>면적: {round(hospital_info['총면적m2'].to_list()[0]/3.3)}평</li>
                            <li>일반의: {int(hospital_info['일반의'].to_list()[0])}명</li>
                            <li>전문의: {int(hospital_info['전문의'].to_list()[0])}명</li>
                            <li>의료장비정보: {hospital_info['의료장비정보'].to_list()[0]}</li>
                        </ul>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
        else:
            st.markdown(
                    f"""
                    <div style='padding: 20px; border: 1px solid #ddd; border-radius: 10px; background-color: #f9f9f9;'>
                        <h2 style='color: black;'>{hospital_info['의원명'].to_list()[0]}</h2>
                        <ul style='list-style-type: disc; padding-left: 10px; color: black;'>
                            <li>주소: {hospital_info['주소'].to_list()[0]}</li>
                            <li>진료과목: {hospital_info['오픈닥터_진료과'].to_list()[0]}</li>
                            <li>개원일자: {hospital_info['개설일자'].to_list()[0]}</li>
                            <li>면적: {round(hospital_info['총면적m2'].to_list()[0]/3.3)}평</li>
                            <li>일반의: {int(hospital_info['일반의'].to_list()[0])}명</li>
                            <li>전문의: {hospital_info['전문의현황'].to_list()[0]} (총 {int(hospital_info['전문의'].to_list()[0])}명)</li>
                            <li>의료장비정보: {hospital_info['의료장비정보'].to_list()[0]}</li>
                        </ul>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
    
    st.markdown("<hr>", unsafe_allow_html=True)

    # x축의 날짜 형식을 YYYYMM으로 설정
    filtered_sales['ta_ym'] = pd.to_datetime(filtered_sales['ta_ym'], format='%Y%m')
    # 억 단위로 변환
    # filtered_sales['est_hga'] = filtered_sales['est_hga'] / 100000000
    
    # Create traces
    trace1 = go.Scatter(
        x=filtered_sales['ta_ym'],
        y=filtered_sales['est_hga'],
        mode='lines+markers+text',
        name='매출',
        line=dict(color='#3955B4', width=5),
        marker=dict(size=10),
        text=filtered_sales['est_hga'],
        textposition='top center',
    )

    # if len(filtered_sales) > 0:
    #     # 최대, 최소값 표기를 위한 마커 데이터 생성
    #     marker_x = [filtered_sales['ta_ym'].iloc[filtered_sales['est_hga'].idxmax()], filtered_sales['ta_ym'].iloc[filtered_sales['est_hga'].idxmin()]]
    #     marker_y = [filtered_sales['est_hga'].max(), filtered_sales['est_hga'].min()]
    #     trace1_markers = go.Scatter(
    #         x=marker_x,
    #         y=marker_y,
    #         mode='markers+text',
    #         name='최대/최소',
    #         marker=dict(size=10, color='red', symbol='circle'),
    #         text=[f"{marker_y[0]:,.0f}억", f"{marker_y[1]:,.0f}억"],
    #         textposition='top right',
    #         textfont=dict(size=12, color='red')  # 텍스트 크기와 색상 설정
    #     )

    trace2 = go.Bar(
        x=filtered_sales['ta_ym'],
        y=filtered_sales['est_cnt'],
        name='진료 건수',
        yaxis='y2',
        opacity=0.3,
        marker=dict(color='gray')
    )

    layout = go.Layout(
        title=dict(
            text='{}'.format(st.session_state.selected_hospital_name),
            font=dict(size=20),  # 제목 글씨 크기
        ),
        xaxis=dict(title='날짜', showgrid=True, zeroline=True),
        yaxis=dict(title='매출', showline=True, zeroline=True),
        yaxis2=dict(title='진료 건수', overlaying='y', side='right',
                    showgrid=False, zeroline=True, layer='above traces',),
        hovermode='closest',
        legend=dict(x=0, y=1.2, orientation="h"),
        margin=dict(t=150)  # 그래프와 테두리 사이 간격
    )


    fig = go.Figure(data=[trace1, trace2], layout=layout)
    st.plotly_chart(fig, theme='streamlit')

# 반경 내 병원 목록 필터링 함수
def render_hospitals_within_radius(selected_code, filtered_hospitals):
    st.sidebar.markdown("<hr>", unsafe_allow_html=True)
    st.sidebar.subheader("반경 내 병원 목록")
    radius = st.sidebar.number_input("반경(m)을 입력해주세요:", min_value=0, max_value=5000, value=500, step=100, key='filter_radius')

    lon = filtered_hospitals[filtered_hospitals['코드'] == selected_code]['x좌표'].to_list()[0]
    lat = filtered_hospitals[filtered_hospitals['코드'] == selected_code]['y좌표'].to_list()[0]

    filtered_hospitals['거리'] = filtered_hospitals.apply(lambda row: distance((lat, lon), (row['y좌표'], row['x좌표'])).meters, axis=1)
    hospitals_within_radius = filtered_hospitals[filtered_hospitals['거리'] <= radius]
    hospitals_within_radius = hospitals_within_radius.sort_values(by='거리', ascending=True)
    # 자기 자신은 빼기
    hospitals_within_radius = hospitals_within_radius[hospitals_within_radius['코드'] != selected_code]
    hospitals_within_radius = hospitals_within_radius.sort_values(by=['거리', '코드'], ascending=[True, False]).drop_duplicates(subset=['의원명', '정제주소'], keep='first')
    st.session_state.hospitals_within_radius = hospitals_within_radius

    # selectbox로 병원 선택
    # 이 때, 선택지는 "병원 이름, 거리"로 표시 
    unique_hospital_names = hospitals_within_radius['의원명'].unique()
    unique_hospital_names = [f"{name}, {distance:.1f}m" for name, distance in zip(unique_hospital_names, hospitals_within_radius[hospitals_within_radius['의원명'].isin(unique_hospital_names)]['거리'])]
    selected_hospital_name = st.sidebar.selectbox(
        "반경 내 원하는 병원을 선택하세요:",
        unique_hospital_names, 
        key='filter_hospital_name_within_radius'
    )
    selected_radius_code = hospitals_within_radius[hospitals_within_radius['의원명'] == selected_hospital_name.split(",")[0]]['코드'].values[0]
    st.session_state.selected_radius_code = selected_radius_code

    # 적용 버튼
    apply_button_radius_2 = st.sidebar.button('적용', key='filter_apply_radius_2')
    if apply_button_radius_2:
        st.write("반경 내 병원 현황")
        if len(hospitals_within_radius) > 0:
            st.dataframe(hospitals_within_radius.style.set_properties(**{
                'background-color': 'white',
                'color': 'black',
                'border-color': 'black',
                'font-size': '14px',
            }), hide_index=True)
        else:
            st.write("")
            st.sidebar.write("반경 내 병원이 없습니다.")



    # filtered_sales = st.session_state.[st.session_state.filtered_sales['코드'] == selected_radius_code]
    # # x축의 날짜 형식을 YYYYMM으로 설정
    # filtered_sales['ta_ym'] = pd.to_datetime(filtered_sales['ta_ym'], format='%Y%m')
    # # 억 단위로 변환
    # filtered_sales['est_hga'] = filtered_sales['est_hga'] / 100000000

    # # Create traces
    # trace1 = go.Scatter(
    #     x=filtered_sales['ta_ym'],
    #     y=filtered_sales['est_hga'],
    #     mode='lines+markers',
    #     name='매출',
    #     line=dict(color='blue'),
    #     marker=dict(size=8)
    # )

    # trace2 = go.Bar(
    #     x=filtered_sales['ta_ym'],
    #     y=filtered_sales['est_cnt'],
    #     name='진료 건수',
    #     yaxis='y2',
    #     opacity=0.5,
    #     marker=dict(color='green')
    # )

    # layout = go.Layout(
    #     title=dict(
    #         text='{}'.format(st.session_state.selected_hospital_name),
    #         font=dict(size=20),  # 제목 글씨 크기
    #     ),
    #     xaxis=dict(title='날짜', showgrid=True, zeroline=True),
    #     yaxis=dict(title='매출 (억)', showline=True, zeroline=True),
    #     yaxis2=dict(title='진료 건수', overlaying='y', side='right', showline=True, zeroline=True),
    #     hovermode='closest',
    #     legend=dict(x=0, y=1.2, orientation="h"),
    #     margin=dict(t=150)  # 그래프와 테두리 사이 간격
    # )

    # fig = go.Figure(data=[trace1, trace2], layout=layout)
    # st.plotly_chart(fig, theme='streamlit')

def render_naver_map_link(code):
    if code:
        encoded_name = urllib.parse.quote(code)
        naver_map_url = f"https://map.naver.com/v5/search/{encoded_name}"

        st.sidebar.markdown(f'''<a href="{naver_map_url}" target="_blank">
                            네이버 지도에서 확인</a>''', unsafe_allow_html=True)

def render_plot(filtered_sales, title_suffix=""):
    # x축의 날짜 형식을 YYYYMM으로 설정
    filtered_sales['ta_ym'] = pd.to_datetime(filtered_sales['ta_ym'], format='%Y%m')
    # 억 단위로 변환
    filtered_sales['est_hga'] = filtered_sales['est_hga'] / 100000000
    # 최대, 최소값 표기를 위한 마커 데이터 생성
    marker_x = [filtered_sales['ta_ym'].iloc[filtered_sales['est_hga'].idxmax()], filtered_sales['ta_ym'].iloc[filtered_sales['est_hga'].idxmin()]]
    marker_y = [filtered_sales['est_hga'].max(), filtered_sales['est_hga'].min()]

    # Create traces
    trace1 = go.Scatter(
        x=filtered_sales['ta_ym'],
        y=filtered_sales['est_hga'],
        mode='lines+markers',
        name='매출',
        line=dict(color='blue'),
        marker=dict(size=8)
    )
    
    trace1_markers = go.Scatter(
        x=marker_x,
        y=marker_y,
        mode='markers',
        name='최대/최소',
        marker=dict(size=10, color='red', symbol='circle')
    )

    trace2 = go.Bar(
        x=filtered_sales['ta_ym'],
        y=filtered_sales['est_cnt'],
        name='진료 건수',
        yaxis='y2',
        opacity=0.5,
        marker=dict(color='green')
    )

    layout = go.Layout(
        title=dict(
            text='{}'.format(title_suffix),
            font=dict(size=20),  # 제목 글씨 크기
        ),
        xaxis=dict(title='날짜', showgrid=True, zeroline=True),
        yaxis=dict(title='매출 (억)', showline=True, zeroline=True),
        yaxis2=dict(title='진료 건수', overlaying='y', side='right', showgrid=False, zeroline=True, layer='above traces'),
        hovermode='closest',
        legend=dict(x=0, y=1.2, orientation="h"),
        margin=dict(t=150)  # 그래프와 테두리 사이 간격
    )

    fig = go.Figure(data=[trace1, trace1_markers, trace2], layout=layout)
    st.plotly_chart(fig, theme='streamlit')

if __name__ == "__main__":
    initialize_session_state()

    if 'initial_hospitals' not in st.session_state:
        progress_bar = st.progress(0)
        progress_bar.progress(10)
        hospitals = load_hospitals(this_date)
        progress_bar.progress(30)
        hospital_sales = load_hospital_sales()
        progress_bar.progress(50)
        dongs = load_dongs()

        st.session_state['initial_hospitals'] = hospitals
        st.session_state['initial_sales'] = hospital_sales
        st.session_state['dong_data'] = dongs

        progress_bar.progress(100)
        progress_bar.empty()

    render_sidebar_filters(st.session_state['initial_hospitals'], st.session_state['dong_data'])

    if st.session_state.filtered_hospitals is not None:
        hospital_name = render_filtered_data_hosname(st.session_state.filtered_hospitals)
        hospital_address = render_filtered_data_hosaddress(st.session_state.filtered_hospitals, hospital_name)
        apply_button = st.sidebar.button('적용', key='filter_apply_hospital')
        if apply_button:
            st.session_state.selected_hospital_name = hospital_name
            st.session_state.selected_hospital_address = hospital_address

            if st.session_state.selected_hospital_name and st.session_state.selected_hospital_address:
                selected_code = st.session_state.filtered_hospitals[(st.session_state.filtered_hospitals['의원명'] == st.session_state.selected_hospital_name) & (st.session_state.filtered_hospitals['정제주소'] == st.session_state.selected_hospital_address)]['코드'].values[0]
                if selected_code != st.session_state.selected_code:
                    st.session_state.selected_code = selected_code
            
        if st.session_state.selected_code and st.session_state.filtered_hospitals is not None:
            render_naver_map_link(st.session_state.selected_code)
            mct_brn_list = list(st.session_state.initial_sales[st.session_state.initial_sales['코드'] == st.session_state.selected_code]['mct_brn'].unique())
            filtered_sales = st.session_state.initial_sales[(st.session_state.initial_sales['mct_brn'].isin(mct_brn_list)) & (st.session_state.initial_sales['ta_ym'].astype(int) >= int(st.session_state.selected_ym[0])) & (st.session_state.initial_sales['ta_ym'].astype(int) <= int(st.session_state.selected_ym[1])) & (st.session_state.initial_sales['est_hga'] >= st.session_state.selected_range[0]) & (st.session_state.initial_sales['est_hga'] <= st.session_state.selected_range[1])]
            st.session_state.filtered_sales = filtered_sales.groupby(['ta_ym', 'mct_brn']).agg({'est_hga': 'sum', 'est_cnt': 'sum'}).reset_index().sort_values(by='ta_ym', ascending=True)
            render_table(st.session_state.filtered_sales, st.session_state.selected_code, st.session_state.filtered_sales)
            # render_plot(st.session_state.filtered_sales, title_suffix="{}".format(st.session_state.selected_hospital_name))
            # render_plot(st.session_state.filtered_sales, title_suffix="{}".format(st.session_state.selected_radius_code))
            render_hospitals_within_radius(st.session_state.selected_code, st.session_state.filtered_hospitals)