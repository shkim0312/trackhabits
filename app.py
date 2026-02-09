# app.py
import os
import re
from datetime import date, timedelta

import altair as alt
import pandas as pd
import requests
import streamlit as st

# ----------------------------
# Page config
# ----------------------------
st.set_page_config(page_title="AI 습관 트래커", page_icon="📊", layout="wide")
st.title("📊 AI 습관 트래커")

# ----------------------------
# Sidebar: API keys
# ----------------------------
with st.sidebar:
    st.header("🔑 API 설정")
    openai_api_key = st.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
    weather_api_key = st.text_input("OpenWeatherMap API Key", type="password", value=os.getenv("OPENWEATHER_API_KEY", ""))
    st.caption("키는 세션에만 사용되며, 앱 종료 시 초기화됩니다.")

# ----------------------------
# Helpers: APIs
# ----------------------------
def get_weather(city: str, api_key: str):
    """
    OpenWeatherMap 현재 날씨 조회 (한국어, 섭씨)
    실패 시 None 반환
    """
    if not city or not api_key:
        return None
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": api_key, "units": "metric", "lang": "kr"}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()

        desc = (data.get("weather") or [{}])[0].get("description")
        temp = (data.get("main") or {}).get("temp")
        feels = (data.get("main") or {}).get("feels_like")
        humidity = (data.get("main") or {}).get("humidity")

        icon = (data.get("weather") or [{}])[0].get("icon")
        icon_url = f"https://openweathermap.org/img/wn/{icon}@2x.png" if icon else None

        return {
            "city": city,
            "description": desc,
            "temp_c": temp,
            "feels_like_c": feels,
            "humidity": humidity,
            "icon_url": icon_url,
        }
    except Exception:
        return None


def _parse_dog_breed_from_url(img_url: str):
    """
    Dog CEO 이미지 URL에서 품종 추정.
    예) .../breeds/hound-afghan/n02088094_1003.jpg -> Hound / Afghan
    """
    if not img_url:
        return None
    m = re.search(r"/breeds/([^/]+)/", img_url)
    if not m:
        return None
    token = m.group(1)  # e.g., "hound-afghan" or "pug"
    parts = token.split("-")
    if len(parts) == 1:
        return parts[0].replace("_", " ").title()
    # 일반적으로 "breed-subbreed" 형태가 많음
    breed = parts[0].replace("_", " ").title()
    sub = " ".join(parts[1:]).replace("_", " ").title()
    return f"{breed} / {sub}"


def get_dog_image():
    """
    Dog CEO에서 랜덤 강아지 사진 URL과 품종 가져오기
    실패 시 None 반환
    """
    try:
        url = "https://dog.ceo/api/breeds/image/random"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        img_url = data.get("message")
        breed = _parse_dog_breed_from_url(img_url)
        return {"image_url": img_url, "breed": breed}
    except Exception:
        return None


def _system_prompt_for_style(style: str) -> str:
    if style == "스파르타 코치":
        return (
            "너는 매우 엄격하고 직설적인 습관 코치다. 변명은 받아주지 않는다. "
            "하지만 공격적이거나 모욕적이면 안 된다. 실행 가능한 지시를 짧고 강하게 준다."
        )
    if style == "따뜻한 멘토":
        return (
            "너는 공감과 격려가 뛰어난 따뜻한 멘토다. 사용자의 감정 상태를 배려하며 "
            "작은 성공을 칭찬하고, 부담 없는 다음 행동을 제안한다."
        )
    # 게임 마스터
    return (
        "너는 RPG 게임 마스터다. 사용자의 하루를 퀘스트/스탯/보상 느낌으로 재구성한다. "
        "유쾌하지만 과도하게 길지 않게, 게임 톤을 유지한다."
    )


def generate_report(
    *,
    habits: dict,
    mood: int,
    weather: dict | None,
    dog: dict | None,
    coach_style: str,
    openai_key: str,
):
    """
    습관+기분+날씨+강아지 품종을 모아 OpenAI에 전달해 리포트 생성
    실패 시 None 반환
    """
    if not openai_key:
        return None

    # ---- assemble input ----
    checked = [k for k, v in habits.items() if v]
    unchecked = [k for k, v in habits.items() if not v]

    weather_text = "날씨 정보 없음"
    if weather:
        weather_text = (
            f"{weather.get('city')} / {weather.get('description','-')} / "
            f"{weather.get('temp_c','-')}°C (체감 {weather.get('feels_like_c','-')}°C) / "
            f"습도 {weather.get('humidity','-')}%"
        )

    dog_text = "강아지 정보 없음"
    if dog:
        dog_text = f"{dog.get('breed') or '품종 미상'} / {dog.get('image_url') or '-'}"

    # ---- OpenAI call (tries new SDK first, then legacy) ----
    system = _system_prompt_for_style(coach_style)
    user_prompt = f"""
[오늘 체크인 데이터]
- 날짜: {date.today().isoformat()}
- 기분(1~10): {mood}

[습관 체크]
- 완료: {", ".join(checked) if checked else "없음"}
- 미완료: {", ".join(unchecked) if unchecked else "없음"}

[날씨]
- {weather_text}

[랜덤 강아지]
- {dog_text}

[출력 형식(반드시 지켜)]
1) 컨디션 등급: S/A/B/C/D 중 하나
2) 습관 분석: 오늘 잘한 점 2개 + 개선할 점 2개 (불릿)
3) 날씨 코멘트: 1~2문장
4) 내일 미션: 딱 3개 (체크박스 형태로 보이게)
5) 오늘의 한마디: 1문장 (코치 스타일 유지)
"""
    try:
        # New SDK: openai>=1.0
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=openai_key)
        resp = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt.strip()},
            ],
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception:
        # Legacy SDK fallback: openai<1.0
        try:
            import openai  # type: ignore

            openai.api_key = openai_key
            resp = openai.ChatCompletion.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt.strip()},
                ],
            )
            return (resp["choices"][0]["message"]["content"] or "").strip() or None
        except Exception:
            return None


# ----------------------------
# Session state: records
# ----------------------------
def _init_demo_records():
    # 데모 6일 + (오늘은 UI 입력으로 채워서 7일 만들 예정)
    # date 오름차순
    base = date.today() - timedelta(days=6)
    demo = [
        {"date": (base + timedelta(days=0)).isoformat(), "ach_rate": 40, "checked": 2, "mood": 5},
        {"date": (base + timedelta(days=1)).isoformat(), "ach_rate": 60, "checked": 3, "mood": 6},
        {"date": (base + timedelta(days=2)).isoformat(), "ach_rate": 80, "checked": 4, "mood": 7},
        {"date": (base + timedelta(days=3)).isoformat(), "ach_rate": 20, "checked": 1, "mood": 4},
        {"date": (base + timedelta(days=4)).isoformat(), "ach_rate": 100, "checked": 5, "mood": 8},
        {"date": (base + timedelta(days=5)).isoformat(), "ach_rate": 60, "checked": 3, "mood": 6},
    ]
    return demo


if "records" not in st.session_state:
    st.session_state.records = _init_demo_records()

if "last_report" not in st.session_state:
    st.session_state.last_report = None

if "last_weather" not in st.session_state:
    st.session_state.last_weather = None

if "last_dog" not in st.session_state:
    st.session_state.last_dog = None


def upsert_today_record(ach_rate: int, checked: int, mood: int):
    today_str = date.today().isoformat()
    found = False
    for r in st.session_state.records:
        if r["date"] == today_str:
            r.update({"ach_rate": ach_rate, "checked": checked, "mood": mood})
            found = True
            break
    if not found:
        st.session_state.records.append({"date": today_str, "ach_rate": ach_rate, "checked": checked, "mood": mood})

    # 최근 7일만 유지(요구사항: 6일 샘플 + 오늘로 7일)
    st.session_state.records = sorted(st.session_state.records, key=lambda x: x["date"])[-7:]


# ----------------------------
# UI: Habit check-in
# ----------------------------
st.subheader("✅ 오늘의 체크인")

left, right = st.columns([1.2, 1])

with left:
    st.markdown("**습관 체크**")

    col1, col2 = st.columns(2)
    with col1:
        wake = st.checkbox("🌅 기상 미션")
        water = st.checkbox("💧 물 마시기")
        study = st.checkbox("📚 공부/독서")
    with col2:
        운동 = st.checkbox("🏃 운동하기")
        sleep = st.checkbox("😴 수면")

    mood = st.slider("🙂 기분 점수 (1~10)", min_value=1, max_value=10, value=6)

with right:
    st.markdown("**환경 & 코치 설정**")
    cities = ["Seoul", "Busan", "Incheon", "Daegu", "Daejeon", "Gwangju", "Ulsan", "Suwon", "Jeju", "Sejong"]
    city = st.selectbox("도시 선택", cities, index=0)
    coach_style = st.radio("코치 스타일", ["스파르타 코치", "따뜻한 멘토", "게임 마스터"], horizontal=False)

habits = {
    "기상 미션": wake,
    "물 마시기": water,
    "공부/독서": study,
    "운동하기": 운동,
    "수면": sleep,
}
checked_count = sum(1 for v in habits.values() if v)
ach_rate = int(round((checked_count / 5) * 100))

# ----------------------------
# Metrics + chart
# ----------------------------
st.subheader("📈 달성률 요약")

m1, m2, m3 = st.columns(3)
m1.metric("달성률", f"{ach_rate}%", help="오늘 체크된 습관 개수 / 5")
m2.metric("달성 습관", f"{checked_count}/5")
m3.metric("기분", f"{mood}/10")

# 오늘 기록을 세션에 반영 (항상 최신 상태로 7일 차트 유지)
upsert_today_record(ach_rate=ach_rate, checked=checked_count, mood=mood)

df = pd.DataFrame(st.session_state.records)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date")

chart = (
    alt.Chart(df)
    .mark_bar()
    .encode(
        x=alt.X("date:T", title="날짜", axis=alt.Axis(format="%m-%d")),
        y=alt.Y("ach_rate:Q", title="달성률(%)", scale=alt.Scale(domain=[0, 100])),
        tooltip=[
            alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
            alt.Tooltip("ach_rate:Q", title="달성률(%)"),
            alt.Tooltip("checked:Q", title="체크 수"),
            alt.Tooltip("mood:Q", title="기분"),
        ],
    )
    .properties(height=260)
)
st.altair_chart(chart, use_container_width=True)

# ----------------------------
# Calendar view
# ----------------------------
st.subheader("🗓️ 달력 보기")

if "selected_date" not in st.session_state:
    st.session_state.selected_date = date.today()

view_mode = st.radio("보기 모드", ["주간", "월간"], horizontal=True)

records_by_date = {
    row["date"].date(): {
        "ach_rate": int(row["ach_rate"]),
        "checked": int(row["checked"]),
        "mood": int(row["mood"]),
    }
    for _, row in df.iterrows()
}

min_record_date = df["date"].min().date() if not df.empty else date.today()
max_record_date = df["date"].max().date() if not df.empty else date.today()

def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)

def _next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _month_range(start: date, end: date) -> list[date]:
    months = []
    cursor = _month_start(start)
    last = _month_start(end)
    while cursor <= last:
        months.append(cursor)
        cursor = _next_month(cursor)
    return months


if view_mode == "월간":
    month_options = _month_range(min_record_date, max_record_date)
    default_month = _month_start(date.today())
    if default_month not in month_options:
        month_options.append(default_month)
        month_options = sorted(month_options)

    month_labels = [m.strftime("%Y-%m") for m in month_options]
    default_index = month_options.index(default_month)
    selected_label = st.selectbox("월 선택", month_labels, index=default_index)
    selected_month = month_options[month_labels.index(selected_label)]

    first_day = selected_month
    next_month = _next_month(first_day)
    last_day = next_month - timedelta(days=1)
    start_weekday = first_day.weekday()  # Monday=0
    total_days = last_day.day

    day_headers = ["월", "화", "수", "목", "금", "토", "일"]
    header_cols = st.columns(7)
    for idx, day_name in enumerate(day_headers):
        header_cols[idx].markdown(f"**{day_name}**")

    cells = []
    cells.extend([None] * start_weekday)
    cells.extend([date(first_day.year, first_day.month, d) for d in range(1, total_days + 1)])
    while len(cells) % 7 != 0:
        cells.append(None)

    for week_start in range(0, len(cells), 7):
        cols = st.columns(7)
        for idx, day in enumerate(cells[week_start : week_start + 7]):
            with cols[idx]:
                if day is None:
                    st.write("")
                    continue
                record = records_by_date.get(day)
                is_today = day == date.today()
                label = f"{day.day}"
                if is_today:
                    label = f"⭐ {label}"
                if record:
                    label = f"{label}\n{record['ach_rate']}% / 🙂{record['mood']}"
                if st.button(label, key=f"day-{day.isoformat()}"):
                    st.session_state.selected_date = day
else:
    week_start = st.session_state.selected_date - timedelta(days=st.session_state.selected_date.weekday())
    week_days = [week_start + timedelta(days=i) for i in range(7)]
    day_headers = ["월", "화", "수", "목", "금", "토", "일"]
    header_cols = st.columns(7)
    for idx, day_name in enumerate(day_headers):
        header_cols[idx].markdown(f"**{day_name}**")

    cols = st.columns(7)
    for idx, day in enumerate(week_days):
        with cols[idx]:
            record = records_by_date.get(day)
            is_today = day == date.today()
            label = day.strftime("%m/%d")
            if is_today:
                label = f"⭐ {label}"
            if record:
                label = f"{label}\n{record['ach_rate']}% / 🙂{record['mood']}"
            if st.button(label, key=f"week-{day.isoformat()}"):
                st.session_state.selected_date = day

selected_day = st.session_state.selected_date
selected_record = records_by_date.get(selected_day)
st.markdown("#### 📌 선택한 날짜 상세")
if selected_record:
    st.write(f"**날짜:** {selected_day.isoformat()}")
    st.write(f"**달성률:** {selected_record['ach_rate']}%")
    st.write(f"**체크 수:** {selected_record['checked']}개")
    st.write(f"**기분:** {selected_record['mood']}/10")
else:
    st.info("선택한 날짜의 체크인 기록이 아직 없어요.")

# ----------------------------
# Generate report
# ----------------------------
st.subheader("🧠 AI 코치 리포트")

btn = st.button("컨디션 리포트 생성", type="primary", use_container_width=True)

if btn:
    # Fetch external info
    weather = get_weather(city, weather_api_key)
    dog = get_dog_image()

    st.session_state.last_weather = weather
    st.session_state.last_dog = dog

    # Generate AI report
    report = generate_report(
        habits=habits,
        mood=mood,
        weather=weather,
        dog=dog,
        coach_style=coach_style,
        openai_key=openai_api_key,
    )
    st.session_state.last_report = report

# ----------------------------
# Result display
# ----------------------------
w = st.session_state.last_weather
d = st.session_state.last_dog
rpt = st.session_state.last_report

if rpt or w or d:
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### ☁️ 오늘의 날씨")
        if w:
            if w.get("icon_url"):
                st.image(w["icon_url"], width=90)
            st.write(f"**도시:** {w.get('city')}")
            st.write(f"**상태:** {w.get('description', '-')}")
            st.write(f"**기온:** {w.get('temp_c', '-') }°C (체감 {w.get('feels_like_c','-')}°C)")
            st.write(f"**습도:** {w.get('humidity','-')}%")
        else:
            st.info("날씨 정보를 가져오지 못했어요. (API Key/도시/네트워크를 확인해 주세요)")

    with c2:
        st.markdown("### 🐶 랜덤 강아지")
        if d and d.get("image_url"):
            st.image(d["image_url"], use_container_width=True)
            st.caption(f"품종: {d.get('breed') or '품종 미상'}")
        else:
            st.info("강아지 이미지를 가져오지 못했어요. (네트워크를 확인해 주세요)")

    st.markdown("### 📝 AI 코치 리포트")
    if rpt:
        st.markdown(rpt)
    else:
        if btn and not openai_api_key:
            st.warning("OpenAI API Key가 비어 있어 리포트를 생성할 수 없어요. 사이드바에 키를 입력해 주세요.")
        elif btn:
            st.warning("리포트 생성에 실패했어요. (키/모델 접근권한/네트워크를 확인해 주세요)")

    # Shareable text
    st.markdown("### 📣 공유용 텍스트")
    share_lines = []
    share_lines.append(f"📅 {date.today().isoformat()} | 달성률 {ach_rate}% | 기분 {mood}/10")
    share_lines.append(f"✅ 완료: {', '.join([k for k, v in habits.items() if v]) or '없음'}")
    share_lines.append(f"⬜ 미완료: {', '.join([k for k, v in habits.items() if not v]) or '없음'}")
    if w:
        share_lines.append(f"☁️ 날씨: {w.get('city')} / {w.get('description','-')} / {w.get('temp_c','-')}°C")
    if d:
        share_lines.append(f"🐶 오늘의 강아지: {d.get('breed') or '품종 미상'}")
    if rpt:
        share_lines.append("\n🧠 AI 코치 한 줄 요약:")
        # 마지막 줄이 "오늘의 한마디"일 가능성이 높아, 끝부분을 짧게 붙임
        share_lines.append(rpt.strip()[-160:])

    st.code("\n".join(share_lines), language="text")

# ----------------------------
# API 안내
# ----------------------------
with st.expander("ℹ️ API 안내 / 설정 방법"):
    st.markdown(
        """
- **OpenAI API Key**: OpenAI에서 발급한 키를 사이드바에 입력하세요.  
  - 모델은 **gpt-5-mini**를 사용합니다.
- **OpenWeatherMap API Key**: OpenWeatherMap에서 발급한 키를 사이드바에 입력하세요.  
  - 현재 날씨를 **한국어(lang=kr)**, **섭씨(units=metric)**로 가져옵니다.
- **Dog CEO API**: 키 없이 사용 가능합니다. 랜덤 강아지 이미지를 불러옵니다.

**문제 해결 팁**
- 키가 비어 있으면 리포트/날씨가 동작하지 않습니다.
- 네트워크 환경에서 외부 API 호출이 차단될 경우 실패할 수 있습니다.
- 모든 외부 요청은 `timeout=10`이며, 실패 시 `None`을 반환합니다.
"""
    )
