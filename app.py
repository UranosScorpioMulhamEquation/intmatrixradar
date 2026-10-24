from __future__ import annotations

import io
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import NamedTuple

import geonamescache
import pandas as pd
import streamlit as st
import swisseph as swe
from timezonefinder import TimezoneFinder
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import uuid
import os

# ==================== 1. Security & License ====================
KEY_FILE = "license.key"

def get_machine_id():
    return hex(uuid.getnode())

def generate_password(mid):
    digits = ''.join(filter(str.isdigit, mid))
    num = int(digits[:8]) if digits else int(mid.encode().hex(), 16)
    return str(round(abs(num / 2 * 3.14)))[:6]

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = os.path.exists(KEY_FILE)

if not st.session_state['authenticated']:
    st.set_page_config(page_title="Security Activation", layout="centered")
    st.title("🔑 Security Activation")
    st.warning("Send your Machine ID to programmer email : mulham81ahmed@gmail.com")

    mid = get_machine_id()
    st.info(f"Machine ID: {mid}")
    pwd = st.text_input("Enter Activation Key:", type="password")
    if st.button("Activate"):
        if pwd == generate_password(mid):
            with open(KEY_FILE, "w") as f: f.write(pwd)
            st.session_state['authenticated'] = True
            st.rerun()
        else:
            st.error("Invalid Activation Key.")
    st.stop()

# ==========================================

# ==================== إعدادات Swiss Ephemeris ====================
swe.set_ephe_path('')  # استخدام وضع Moshier الافتراضي للتقويم الفلكي الدقيق

# ==================== الثوابت وقوائم الكواكب والحكام ====================

TARGET_PLANETS = ['Mars', 'Rahu', 'Ketu', 'Saturn', 'Neptune', 'Uranus', 'Pluto']
SLOW_PLANETS = ['Jupiter', 'Saturn', 'Uranus', 'Neptune', 'Pluto']
HAZARD_CONJUNCT_PLANETS = ['Rahu', 'Ketu', 'Mars', 'Pluto', 'Neptune', 'Uranus', 'Saturn']

# الحفاظ على معايير نظرية سنوات الخطر الأصلية (أوربت الأوتاد 6 درجات)
ORB = 3.0             
ANGULAR_ORB = 6.0     
URANUS_CYCLE_DIVISOR = 4.2857  

PLANET_IDS = {
    'Sun': swe.SUN,
    'Moon': swe.MOON,
    'Mars': swe.MARS,
    'Jupiter': swe.JUPITER,
    'Saturn': swe.SATURN,
    'Uranus': swe.URANUS,
    'Neptune': swe.NEPTUNE,
    'Pluto': swe.PLUTO,
    'Rahu': swe.MEAN_NODE,
    'Ketu': -1,
}

PLANET_NAMES_AR = {
    'Sun': 'الشمس',
    'Moon': 'القمر',
    'Mars': 'المريخ',
    'Jupiter': 'المشتري',
    'Saturn': 'زحل',
    'Uranus': 'أورانوس',
    'Neptune': 'نبتون',
    'Pluto': 'بلوتو',
    'Rahu': 'راخو (العقدة الشمالية)',
    'Ketu': 'كيتو (العقدة الجنوبية)'
}

SIGN_RULERS = {
    0: ['Mars'],               
    1: ['Venus'],              
    2: ['Mercury'],            
    3: ['Moon'],               
    4: ['Sun'],                
    5: ['Mercury'],            
    6: ['Venus'],              
    7: ['Mars', 'Pluto'],      
    8: ['Jupiter'],            
    9: ['Saturn'],             
    10: ['Saturn', 'Uranus'],  
    11: ['Jupiter', 'Neptune'] 
}

class City(NamedTuple):
    geonameid: str
    name: str
    country_code: str
    latitude: float
    longitude: float
    admin1: str
    population: int

@dataclass
class MundaneYearRow:
    year: int
    age: int
    energy: int
    economy: str
    econ_pos: bool
    politics: str
    pol_pos: bool
    population: str
    pop_pos: bool
    security: str
    sec_pos: bool
    war: str
    is_war: bool
    meaning: str
    risk_power: str
    trigger_planets: str
    mechanism: str
    quarter: str
    hazard_months: str
    risk_percentage: str
    risk_val: int

# ==================== تحميل البيانات الجغرافية ====================

@st.cache_resource
def load_cities() -> list[City]:
    gc = geonamescache.GeonamesCache()
    cities_list = []
    for city_id, city_data in gc.get_cities().items():
        if city_data.get("population", 0) >= 15000:
            cities_list.append(
                City(
                    geonameid=city_id,
                    name=city_data.get("name", ""),
                    country_code=city_data.get("countrycode", ""),
                    latitude=city_data.get("latitude", 0.0),
                    longitude=city_data.get("longitude", 0.0),
                    admin1=city_data.get("admin1code", ""),
                    population=city_data.get("population", 0),
                )
            )
    return cities_list

@st.cache_resource
def load_countries() -> dict:
    gc = geonamescache.GeonamesCache()
    return gc.get_countries()

def get_cities_by_country(country_code: str) -> list[City]:
    cities = load_cities()
    return sorted(
        [c for c in cities if c.country_code == country_code],
        key=lambda c: c.population,
        reverse=True,
    )

def get_timezone_for_city(city: City) -> str | None:
    try:
        tf = TimezoneFinder()
        return tf.timezone_at(lat=city.latitude, lng=city.longitude)
    except Exception:
        return None

# ==================== الحسابات الفلكية وأدوات المصفوفة ====================

def reduce_to_22(n):
    if n <= 22:
        return n if n > 0 else 22
    while n > 22:
        n = sum(int(digit) for digit in str(n))
        if n == 0:
            return 22
    return n

def calculate_system_matrix(found_date):
    day = found_date.day
    month = found_date.month
    year = found_date.year

    p1 = reduce_to_22(day)
    p2 = reduce_to_22(month)
    year_sum = sum(int(d) for d in str(year))
    p3 = reduce_to_22(year_sum)

    p4 = reduce_to_22(p1 + p2 + p3)
    center = reduce_to_22(p1 + p2 + p3 + p4)

    economy_line = reduce_to_22(p1 + p4 + center)
    politics_line = reduce_to_22(p2 + p3 + center)
    security_line = reduce_to_22(p1 + p2 + center)

    return {
        "p1": p1, "p2": p2, "p3": p3, "p4": p4,
        "center": center, "economy_line": economy_line,
        "politics_line": politics_line, "security_line": security_line,
    }

ENERGY_MEANINGS = {
    1: "طاقة الريادة والابتكار المؤسسي: إعادة هيكلة البنية التحتية والسيادية.",
    2: "طاقة الدبلوماسية والسياسات الخفية: اتفاقيات غير معلنة وإدارة أزمات صامتة.",
    3: "طاقة الوفرة والنمو: ازدهار القطاعات الإنتاجية والتجارية للنظام.",
    4: "طاقة السلطة المركزية والنظام الصارم: بسط النفوذ وتثبيت أركان الدولة.",
    5: "طاقة التشريع والدستور: تفعيل القوانين وتطوير المنظومة التعليمية والقضائية.",
    6: "طاقة الشراكات والاختيارات: معاهدات، تجاذبات سياسية، واختبارات انسجام مجتمعي.",
    7: "طاقة التوسع والنفوذ الميداني: تحركات عسكرية وحشود استراتيجية حاسمة.",
    8: "طاقة الميزانية والتوازن القومي: ضبط النفقات والتسويات القانونية والمالية.",
    9: "طاقة التركيز الداخلي: الانكفاء الإيجابي لتطوير البحوث والقدرات الذاتية.",
    10: "طاقة التحولات المفاجئة: تقلبات جيوسياسية وانعطافات حاسمة في المسار.",
    11: "طاقة الحشد والقوة الميدانية: مواجهات واختبار حقيقي للجاهزية والقبضة الأمنية.",
    12: "طاقة الضغوط والابتلاءات: تباطؤ في الإنتاج، ركود، وتضحيات تفرضها الظروف.",
    13: "طاقة التحول الجذري والثورات: هدم هياكل سابقة وإعادة صياغة كاملة للنظام.",
    14: "طاقة التوازن والاستقرار: مرحلة تعافٍ وتناغم بين المؤسسات والمجتمع.",
    15: "طاقة الضغوط والمواجهات الخفية: تمردات، مواجهات، واختبارات قاسية للنظام.",
    16: "طاقة الصدمات والهزات العنيفة: أزمات طارئة، ثورات، واهتزازات تختبر تماسك السلطة.",
    17: "طاقة التألق والإشعاع: مشاريع مستقبلية كبرى وثقة دولية متصاعدة.",
    18: "طاقة الحروب النفسية والدعاية: توترات، تحريك للشارع، واختبارات للرأي العام.",
    19: "طاقة الازدهار العظيم: استقرار شامل، رفاهية، وإنجازات تنموية مشهودة.",
    20: "طاقة الإصلاح الشامل والبعث: صحوة هيكلية وتجديد الدماء في القيادة.",
    21: "طاقة العالم والاندماج الدولي: انفتاح خارجي واسع وترسيخ مكانة الدولة.",
    22: "طاقة المفاجآت والحرية: خروج عن النمط التقليدي وتحولات غير متوقعة.",
}

def get_energy_meaning(energy_num):
    return ENERGY_MEANINGS.get(energy_num, "طاقة دورية تؤثر على قرارات النظام السياسي ومساره.")

def get_quarter_string(month: int) -> str:
    if 1 <= month <= 3:
        return "الربع الأول (Q1)"
    elif 4 <= month <= 6:
        return "الربع الثاني (Q2)"
    elif 7 <= month <= 9:
        return "الربع الثالث (Q3)"
    else:
        return "الربع الرابع (Q4)"

def get_julian_day(dt_utc: datetime) -> float:
    decimal_hour = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, decimal_hour)

def get_planet_longitude(planet_name: str, dt_utc: datetime) -> float:
    jd = get_julian_day(dt_utc)
    if planet_name == 'Ketu':
        rahu_pos = swe.calc_ut(jd, swe.MEAN_NODE)[0][0]
        return (rahu_pos + 180.0) % 360.0
    planet_id = PLANET_IDS.get(planet_name)
    if planet_id is not None:
        res = swe.calc_ut(jd, planet_id)
        return res[0][0]
    raise ValueError(f"اسم الكوكب غير معروف: {planet_name}")

def calculate_whole_sign_houses(ascendant_longitude: float) -> dict[int, float]:
    ascendant_sign = int(ascendant_longitude // 30)
    houses = {}
    for i in range(12):
        house_number = i + 1
        sign_index = (ascendant_sign + i) % 12
        houses[house_number] = sign_index * 30.0
    return houses

def is_within_orb(pos1: float, pos2: float, orb: float = ORB) -> bool:
    diff = abs(pos1 - pos2)
    diff = min(diff, 360.0 - diff)
    return diff <= orb

def is_planet_ruler_or_near_asc(planet_name: str, transit_dt: datetime, natal_asc: float, natal_rulers: list[str]) -> bool:
    if planet_name in natal_rulers:
        return True
    planet_pos = get_planet_longitude(planet_name, transit_dt)
    if is_within_orb(planet_pos, natal_asc, ORB):
        return True
    for h_p in HAZARD_CONJUNCT_PLANETS:
        if h_p == planet_name:
            continue
        h_pos = get_planet_longitude(h_p, transit_dt)
        t_pos = get_planet_longitude(planet_name, transit_dt)
        if is_within_orb(h_pos, t_pos, ORB):
            if h_p in natal_rulers or is_within_orb(h_pos, natal_asc, ORB):
                return True
    return False

# ==================== الدالة الرئيسية للتطبيق ====================

def libephemeris():
    st.set_page_config(page_title="المحلل الخبير للتنجيم الدولي ومصفوفة الأمم", layout="wide")
    st.title("🌐 نظام مصفوفة الأمم وخوارزميات خرائط عبور التنجيم الدولي (المدمج بنظرية السنوات الخطرة)")
    st.caption("دمج مصفوفة القدر السياسية مع خرائط العبور الفلكية وتحديد نسب الخطر السنوي - (تطوير الفلكي الدكتور : ملهم احمد)")
    st.markdown("---")

    countries_data = load_countries()
    country_options = {f"{c['name']} ({code})": code for code, c in countries_data.items()}
    sorted_country_names = sorted(country_options.keys())

    col1, col2 = st.columns(2)

    with col1:
        selected_country_label = st.selectbox("اختر الدولة الجغرافية", sorted_country_names)
        selected_country_code = country_options[selected_country_label]
        # استخراج اسم الدولة تلقائياً من الاختيار الجغرافي دون إدخال نصي إضافي
        country_name = selected_country_label.split(' (')[0]

    with col2:
        available_cities = get_cities_by_country(selected_country_code)
        if available_cities:
            city_names = [f"{c.name} (تعداد: {c.population:,})" for c in available_cities]
            selected_city_index = st.selectbox("اختر العاصمة أو المدينة الرئيسية", range(len(city_names)), format_func=lambda x: city_names[x])
            selected_city = available_cities[selected_city_index]
        else:
            st.error("لم يتم العثور على مدن لهذه الدولة.")
            selected_city = None

        foundation_date = st.date_input("تاريخ تأسيس آخر نظام سياسي", min_value=date(1800, 1, 1), max_value=date(2100, 1, 1), value=date(1990, 1, 1))

    st.info(f"الدولة المحددة للتحليل: **{country_name}** | النطاق الزمني المفعل: **120 عاماً** بدءاً من تأسيس النظام السياسي.")

    if st.button("🚀 ابدأ تحليل النظام السياسي ومصفوفة الأخطار الشاملة", type="primary", use_container_width=True):
        if not selected_city:
            st.error("يرجى اختيار مدينة صحيحة.")
            st.stop()

        with st.spinner("جاري حساب مواقع الكواكب وتطبيق نظرية سنوات الخطر الأصلية ضمن دورات أورانوس والأوتاد..."):
            
            tz_str = get_timezone_for_city(selected_city)
            if tz_str:
                try:
                    local_tz = ZoneInfo(tz_str)
                    local_dt = datetime.combine(foundation_date, time(12, 0)).replace(tzinfo=local_tz)
                    utc_dt = local_dt.astimezone(timezone.utc)
                except ZoneInfoNotFoundError:
                    utc_dt = datetime.combine(foundation_date, time(12, 0)).replace(tzinfo=timezone.utc)
            else:
                utc_dt = datetime.combine(foundation_date, time(12, 0)).replace(timezone.utc)

            matrix = calculate_system_matrix(foundation_date)
            f_year = foundation_date.year
            current_year = datetime.now().year

            # البرج الشمسي كطالع اعتباري للنظام
            asc_degree = get_planet_longitude("Sun", utc_dt)
            houses = calculate_whole_sign_houses(asc_degree)
            asc_sign_index = int(asc_degree // 30)
            natal_rulers = SIGN_RULERS.get(asc_sign_index, ['Mars'])

            natal_positions = {}
            distances_from_aries = {}
            for planet in TARGET_PLANETS:
                pos = get_planet_longitude(planet, utc_dt)
                natal_positions[planet] = pos
                distances_from_aries[planet] = pos % 360.0

            angular_houses = [1, 6, 8, 12]
            target_house_cusps = {h: houses[h] for h in angular_houses}

            # ==================== تطبيق نظرية سنوات الخطر الأصلية بدقة ====================
            year_hazard_cache = {}

            for planet, natal_pos in natal_positions.items():
                base_age = distances_from_aries[planet] / URANUS_CYCLE_DIVISOR
                cycles_to_check = [
                    (base_age, "دورة أساسية"),
                    (base_age + 42.0, "دورة المعارضة (42 سنة)"),
                    (base_age + 84.0, "دورة العودة (84 سنة)")
                ]

                for target_age, cycle_label in cycles_to_check:
                    days_to_add = target_age * 365.2425
                    target_utc_date = utc_dt + timedelta(days=days_to_add)
                    current_risk_year = int(target_utc_date.year)

                    if f_year <= current_risk_year <= (f_year + 119):
                        condition_1_met = False
                        active_transits = []
                        matched_mechanisms = []

                        for t_planet in SLOW_PLANETS:
                            t_pos = get_planet_longitude(t_planet, target_utc_date)
                            hit_angle = False

                            for h_num, cusp_deg in target_house_cusps.items():
                                if is_within_orb(t_pos, cusp_deg, ANGULAR_ORB):
                                    hit_angle = True
                                    t_ar = PLANET_NAMES_AR.get(t_planet, t_planet)
                                    matched_mechanisms.append(f"عبور {t_ar} على وتد/بيت ({h_num}) ضمن نطاق (0-6°)")
                                    break
                                if is_within_orb(t_pos, (cusp_deg + ANGULAR_ORB) % 360.0, ORB):
                                    hit_angle = True
                                    t_ar = PLANET_NAMES_AR.get(t_planet, t_planet)
                                    matched_mechanisms.append(f"عبور {t_ar} في نطاق الأوتاد للبيت ({h_num})")
                                    break

                            if hit_angle:
                                condition_1_met = True
                                if t_planet not in active_transits:
                                    active_transits.append(t_planet)

                        condition_2_met = False
                        if condition_1_met:
                            for active_p in active_transits:
                                is_conjunct_hazard = active_p in HAZARD_CONJUNCT_PLANETS
                                if not is_conjunct_hazard:
                                    for h_c in HAZARD_CONJUNCT_PLANETS:
                                        if is_within_orb(get_planet_longitude(active_p, target_utc_date), get_planet_longitude(h_c, target_utc_date), ORB):
                                            is_conjunct_hazard = True
                                            break
                                is_ruler_or_asc = is_planet_ruler_or_near_asc(active_p, target_utc_date, asc_degree, natal_rulers)
                                if is_conjunct_hazard and is_ruler_or_asc:
                                    condition_2_met = True
                                    matched_mechanisms.append("اقتران بحاكم الطالع / اتصالات مدمرة")
                                    break

                        if condition_1_met:
                            risk_power = "خطر شديد جداً (تحول كارثي / أزمة كبرى)" if condition_2_met else "تنبيه خطر متوسط على الأوتاد"
                            trigger_ar = PLANET_NAMES_AR.get(planet, planet)
                            active_ar_list = [PLANET_NAMES_AR.get(p, p) for p in active_transits]
                            trigger_planets_str = f"{trigger_ar} (عبور: {', '.join(active_ar_list)})"
                            mechanism_str = " | ".join(set(matched_mechanisms)) if matched_mechanisms else "عبور كواكب بطيئة على الأوتاد"
                            quarter_str = get_quarter_string(target_utc_date.month)

                            hazard_months_set = set()
                            for m in range(1, 13):
                                sample_dt = datetime(current_risk_year, m, 15, tzinfo=timezone.utc)
                                for tp in active_transits:
                                    tp_pos = get_planet_longitude(tp, sample_dt)
                                    for h_num, cusp_deg in target_house_cusps.items():
                                        if is_within_orb(tp_pos, cusp_deg, ANGULAR_ORB):
                                            hazard_months_set.add(m)

                            if not hazard_months_set:
                                hazard_months_set.add(target_utc_date.month)
                            
                            hazard_months_str = ", ".join([str(m) for m in sorted(list(hazard_months_set))])

                            year_hazard_cache[current_risk_year] = {
                                "risk_power": risk_power,
                                "trigger_planets": trigger_planets_str,
                                "mechanism": mechanism_str,
                                "quarter": quarter_str,
                                "hazard_months": hazard_months_str,
                                "is_hazard": True
                            }

            # ==================== توليد جدول الـ 120 عاماً ومصفوفة الأمم ====================
            timeline_data = []
            for i in range(120):
                yr = f_year + i
                years_passed = i
                yr_energy = reduce_to_22(matrix["center"] + reduce_to_22(yr) + (years_passed % 22))

                is_astrological_hazard = yr in year_hazard_cache

                # 1. تحديد الحروب
                if yr_energy in [13, 16]:
                    war_type = "حرب داخلية (حرب أهلية / تمرد مسلح)"
                    is_war = True
                elif yr_energy in [7, 21]:
                    war_type = "حرب خارجية (صراع عسكري مباشر مع دول)"
                    is_war = True
                elif yr_energy in [15, 18]:
                    war_type = "حرب مختلطة (تمويل خارجي لجماعات بالوكالة)"
                    is_war = True
                else:
                    if is_astrological_hazard and "شديد جداً" in year_hazard_cache[yr]["risk_power"]:
                        war_type = "نزاع مسلح / مواجهات ميدانية خطرة"
                        is_war = True
                    else:
                        war_type = "سلم واستقرار أمني عام"
                        is_war = False

                # 2. تحديد الوضع الأمني
                if is_war or yr_energy in [4, 8, 11, 12, 16] or is_astrological_hazard:
                    sec_status = "استنفار أمني وتشدد بالقبضة الأمنية"
                    sec_pos = False
                else:
                    sec_status = "اعتيادي ومستقر"
                    sec_pos = True

                # 3. تحديد الوضع الاقتصادي (قاعدة: لا رفاهية في الحرب)
                if is_war:
                    econ_type = "صعوبات ومعاناة اقتصادية حادة (تداعيات الحرب)"
                    econ_pos = False
                else:
                    if yr_energy in [3, 10, 19, 21] and not is_astrological_hazard:
                        econ_type = "رفاهية وازدهار اقتصادي كبير"
                        econ_pos = True
                    elif yr_energy in [12, 13, 15, 16] or is_astrological_hazard:
                        econ_type = "معاناة وركود اقتصادي"
                        econ_pos = False
                    else:
                        econ_type = "استقرار اقتصادي ونمو متوازن"
                        econ_pos = True

                # 4. تحديد الوضع السياسي
                if yr_energy in [4, 8, 11, 17, 21] and not is_astrological_hazard:
                    pol_type = "استقرار سياسي وتثبيت دعائم الحكم"
                    pol_pos = True
                else:
                    pol_type = "اضطراب سياسي وإعادة هيكلة للنظام"
                    pol_pos = False

                # 5. تحديد الوضع الشعبي
                if yr_energy in [11, 15, 16, 18, 22] or is_astrological_hazard:
                    pop_type = "اضطراب وتمرد ومظاهرات شعبية"
                    pop_pos = False
                else:
                    pop_type = "استقرار شعبي وهدوء مجتمعي"
                    pop_pos = True

                meaning = get_energy_meaning(yr_energy)

                if is_astrological_hazard:
                    h_info = year_hazard_cache[yr]
                    r_power = h_info["risk_power"]
                    t_planets = h_info["trigger_planets"]
                    mech = h_info["mechanism"]
                    qtr = h_info["quarter"]
                    h_months = h_info["hazard_months"]
                else:
                    r_power = "وضع اعتيادي / مستقر"
                    t_planets = "لا توجد تقاطعات حرجة"
                    mech = "بدون ضغوط عابرة على الأوتاد"
                    qtr = "-"
                    h_months = "-"

                # حساب نسبة الخطر السنوي
                r_score = 10
                if is_war:
                    r_score += 40
                if "شديد جداً" in r_power:
                    r_score += 35
                elif "متوسط" in r_power:
                    r_score += 20
                if not econ_pos:
                    r_score += 15
                if not pop_pos:
                    r_score += 10
                if not sec_pos:
                    r_score += 10
                r_score = min(r_score, 100)
                risk_pct_str = f"{r_score}%"

                timeline_data.append(
                    MundaneYearRow(
                        year=yr,
                        age=years_passed,
                        energy=yr_energy,
                        economy=econ_type,
                        econ_pos=econ_pos,
                        politics=pol_type,
                        pol_pos=pol_pos,
                        population=pop_type,
                        pop_pos=pop_pos,
                        security=sec_status,
                        sec_pos=sec_pos,
                        war=war_type,
                        is_war=is_war,
                        meaning=meaning,
                        risk_power=r_power,
                        trigger_planets=t_planets,
                        mechanism=mech,
                        quarter=qtr,
                        hazard_months=h_months,
                        risk_percentage=risk_pct_str,
                        risk_val=r_score
                    )
                )

            # نصيحة المصفوفة (مبنية حصراً ودقة على: الوضع الاقتصادي + الوضع الشعبي + السلم والحرب)
            historical_years = [y for y in timeline_data if f_year <= y.year <= current_year]
            if historical_years:
                total_hist = len(historical_years)
                pos_hist = sum(
                    1 for y in historical_years 
                    if y.econ_pos and y.pop_pos and (not y.is_war)
                )
                ratio = pos_hist / total_hist if total_hist > 0 else 0

                if ratio >= 0.55:
                    rec_title = "🟢 تنصح بالاستقرار والاستثمار (بيئة اقتصادية وشعبية مستقرة وخالية من الحروب)"
                    rec_desc = f"بناءً على تحليل مؤشرات (الوضع الاقتصادي، المزاج الشعبي، وحالة السلم والحرب) من تأسيس النظام لغاية عام ({current_year})، بلغت نسبة السنوات الإيجابية والمستقرة نحو {ratio*100:.1f}%. البيئة ملائمة للاستثمار."
                elif ratio >= 0.35:
                    rec_title = "🟡 تنصح بالاستقرار بحذر وتوخي الحيطة الاستثمارية"
                    rec_desc = f"بناءً على تتبع مخرجات الاقتصاد، الشارع الشعبي، والحروب لغاية عام {current_year}، تساوت فترات الاستقرار مع فترات الأزمات (نسبة الإيجابية التاريخية {ratio*100:.1f}%). يتطلب الاستثمار مرونة وحذراً."
                else:
                    rec_title = "🔴 لا تنصح بالاستقرار أو ضخ استثمارات طويلة الأجل في الوقت الحالي"
                    rec_desc = f"أظهرت قراءة التاريخ الاقتصادي، الشعبي، وسجل السلم والحرب للنظام لغاية عام {current_year} غلبة واضحة لاقتصادات الحروب والاضطرابات (نسبة الإيجابية التاريخية {ratio*100:.1f}%). البيئة غير آمنة للاستثمارات."
            else:
                rec_title = "⚠️ نطاق زمني حديث"
                rec_desc = "تاريخ تأسيس النظام حديث جداً أو يقع في المستقبل."

            st.success(f"✨ تم إتمام التحليل الجيوسياسي والفلكي الدقيق لكيان ({country_name}) بنجاح لمدى 120 عاماً!")

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("طاقة الحكم والسيادة", matrix["center"])
            col_m2.metric("طاقة السياسات الاقتصادية", matrix["economy_line"])
            col_m3.metric("طاقة الأمن والدفاع", matrix["security_line"])

            st.markdown(f"""
                <div style="background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; border-right: 5px solid #2980b9; direction: rtl; text-align: right;">
                    <h3 style="color: #1b4f72; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px;">📊 البطاقة الاستراتيجية الشاملة للنظام السياسي</h3>
                    <p><b>الدولة / الكيان الجغرافي:</b> {country_name}</p>
                    <p><b>تاريخ تأسيس آخر نظام سياسي:</b> {foundation_date}</p>
                    <p><b>النطاق الزمني للدراسة:</b> من عام {f_year} إلى عام {f_year + 119} (120 عاماً كاملة).</p>
                    <p><b>المنهجية:</b> دمج نظرية سنوات الخطر الفلكية الأصلية بدورة أورانوس والأوتاد مع مصفوفة الأمم الاستراتيجية.</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; border-right: 5px solid #27ae60; direction: rtl; text-align: right;">
                    <h3 style="color: #1b4f72; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px;">💡 نصيحة المصفوفة للاستقرار والاستثمار (حسب الاقتصاد، الشارع، والسلم/الحرب حتى {current_year})</h3>
                    <p><b>القرار التقييمي:</b> <span style="font-size: 16px; font-weight: bold;">{rec_title}</span></p>
                    <p>{rec_desc}</p>
                </div>
            """, unsafe_allow_html=True)

            table_rows = ""
            for item in timeline_data:
                econ_cls = "color: #27ae60; font-weight: bold;" if item.econ_pos else "color: #c0392b; font-weight: bold;"
                pol_cls = "color: #27ae60; font-weight: bold;" if item.pol_pos else "color: #c0392b; font-weight: bold;"
                pop_cls = "color: #27ae60; font-weight: bold;" if item.pop_pos else "color: #c0392b; font-weight: bold;"
                sec_cls = "color: #27ae60; font-weight: bold;" if item.sec_pos else "color: #c0392b; font-weight: bold;"
                war_cls = "color: #c0392b; font-weight: bold;" if item.is_war else "color: #27ae60; font-weight: bold;"
                risk_p_cls = "color: #c0392b; font-weight: bold;" if "شديد جداً" in item.risk_power else ("color: #e67e22; font-weight: bold;" if "متوسط" in item.risk_power else "color: #27ae60;")
                risk_val_color = "#c0392b" if item.risk_val >= 50 else ("#e67e22" if item.risk_val >= 30 else "#27ae60")

                table_rows += f"""
                    <tr>
                        <td>{item.year}</td>
                        <td>{item.age}</td>
                        <td><b>طاقة {item.energy}</b></td>
                        <td style="{econ_cls}">{item.economy}</td>
                        <td style="{pol_cls}">{item.politics}</td>
                        <td style="{pop_cls}">{item.population}</td>
                        <td style="{sec_cls}">{item.security}</td>
                        <td style="{war_cls}">{item.war}</td>
                        <td style="{risk_p_cls}">{item.risk_power}</td>
                        <td style="color: {risk_val_color}; font-weight: bold; text-align: center;">{item.risk_percentage}</td>
                        <td><b>{item.hazard_months}</b> ({item.quarter})</td>
                    </tr>
                """

            st.markdown(f"""
                <div style="background-color: #ffffff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; border-right: 5px solid #2980b9; direction: rtl; text-align: right;">
                    <h3 style="color: #1b4f72; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px;">⏳ سجل الدورات الاستراتيجية ونسبة الخطر (120 عاماً)</h3>
                    <p><span style="color: #27ae60; font-weight: bold;">🟢 الأخضر: إيجابي</span> | <span style="color: #c0392b; font-weight: bold;">🔴 الأحمر: سلبي / خطر مرتفع</span></p>
                    <div style="max-height: 500px; overflow-y: auto; border: 1px solid #ddd; border-radius: 5px; padding: 10px;">
                        <table style="width:100%; border-collapse: collapse; text-align: right;">
                            <thead>
                                <tr style="background-color: #f2f2f2; border-bottom: 2px solid #ddd;">
                                    <th style="padding: 8px;">السنة</th>
                                    <th style="padding: 8px;">عمر النظام</th>
                                    <th style="padding: 8px;">الطاقة</th>
                                    <th style="padding: 8px;">الوضع الاقتصادي</th>
                                    <th style="padding: 8px;">الوضع السياسي</th>
                                    <th style="padding: 8px;">الوضع الشعبي</th>
                                    <th style="padding: 8px;">الوضع الأمني</th>
                                    <th style="padding: 8px;">السلم والحروب</th>
                                    <th style="padding: 8px;">السنوات الخطرة وقوتها</th>
                                    <th style="padding: 8px; text-align: center;">نسبة الخطر</th>
                                    <th style="padding: 8px;">أشهر الخطر المحددة</th>
                                </tr>
                            </thead>
                            <tbody>
                                {table_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            html_table_rows = ""
            for item in timeline_data:
                econ_color = "#27ae60" if item.econ_pos else "#c0392b"
                pol_color = "#27ae60" if item.pol_pos else "#c0392b"
                pop_color = "#27ae60" if item.pop_pos else "#c0392b"
                sec_color = "#27ae60" if item.sec_pos else "#c0392b"
                war_color = "#c0392b" if item.is_war else "#27ae60"
                risk_p_color = "#c0392b" if "شديد جداً" in item.risk_power else ("#e67e22" if "متوسط" in item.risk_power else "#27ae60")
                risk_val_color = "#c0392b" if item.risk_val >= 50 else ("#e67e22" if item.risk_val >= 30 else "#27ae60")

                html_table_rows += f"""
                    <tr>
                        <td style='padding: 5px; border: 1px solid #ddd;'>{item.year}</td>
                        <td style='padding: 5px; border: 1px solid #ddd;'>{item.age}</td>
                        <td style='padding: 5px; border: 1px solid #ddd;'><b>طاقة {item.energy}</b></td>
                        <td style='padding: 5px; border: 1px solid #ddd; color: {econ_color}; font-weight: bold;'>{item.economy}</td>
                        <td style='padding: 5px; border: 1px solid #ddd; color: {pol_color}; font-weight: bold;'>{item.politics}</td>
                        <td style='padding: 5px; border: 1px solid #ddd; color: {pop_color}; font-weight: bold;'>{item.population}</td>
                        <td style='padding: 5px; border: 1px solid #ddd; color: {sec_color}; font-weight: bold;'>{item.security}</td>
                        <td style='padding: 5px; border: 1px solid #ddd; color: {war_color}; font-weight: bold;'>{item.war}</td>
                        <td style='padding: 5px; border: 1px solid #ddd; color: {risk_p_color}; font-weight: bold;'>{item.risk_power}</td>
                        <td style='padding: 5px; border: 1px solid #ddd; color: {risk_val_color}; font-weight: bold; text-align: center;'>{item.risk_percentage}</td>
                        <td style='padding: 5px; border: 1px solid #ddd;'><b>{item.hazard_months}</b> ({item.quarter})</td>
                    </tr>
                """

            html_report = f"""
                <!DOCTYPE html>
                <html lang="ar" dir="rtl">
                <head>
                    <meta charset="UTF-8">
                    <title>التقرير الاستراتيجي الشامل - مصفوفة الأمم ونسب الخطر لكيان {country_name}</title>
                    <style>
                        body {{ font-family: 'Amiri', Tahoma, sans-serif; background-color: #fff; color: #222; padding: 30px; line-height: 1.6; }}
                        .container {{ max-width: 1150px; margin: auto; border: 1px solid #ccc; padding: 30px; border-radius: 10px; }}
                        h1 {{ text-align: center; color: #1a5276; border-bottom: 3px solid #2980b9; padding-bottom: 15px; }}
                        .meta {{ background: #f8f9fa; padding: 15px; border-radius: 6px; margin-bottom: 20px; border-right: 4px solid #1a5276; }}
                        .rec-box {{ background: #f8f9fa; padding: 15px; border-radius: 6px; margin-bottom: 20px; border-right: 4px solid #27ae60; }}
                        .section {{ margin-bottom: 20px; border-bottom: 1px solid #e2e8f0; padding-bottom: 15px; }}
                        h3 {{ color: #1b4f72; margin-bottom: 10px; }}
                        .footer {{ text-align: center; margin-top: 30px; font-size: 11px; color: #7f8c8d; border-top: 1px solid #eee; padding-top: 10px; }}
                        .print-btn {{ background: #1a5276; color: white; padding: 10px 25px; border: none; border-radius: 5px; cursor: pointer; font-size: 15px; display: block; margin: 20px auto; }}
                        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                        th, td {{ border: 1px solid #ddd; padding: 5px; text-align: right; font-size: 10px; }}
                        th {{ background-color: #f2f2f2; color: #1a5276; }}
                        @media print {{ .print-btn {{ display: none; }} }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>التقرير الاستراتيجي الجيوسياسي - مصفوفة الأمم ونسب الخطر</h1>
                        <div class="meta">
                            <p><b>الدولة / الكيان:</b> {country_name}</p>
                            <p><b>تاريخ تأسيس آخر نظام سياسي:</b> {foundation_date}</p>
                            <p><b>النطاق الزمني للتحليل:</b> 120 عاماً (من سنة {f_year} إلى سنة {f_year + 119})</p>
                            <p><b>طاقات السيادة الحاكمة:</b> الحكم ({matrix['center']}) | الاقتصاد ({matrix['economy_line']}) | الأمن ({matrix['security_line']})</p>
                        </div>

                        <div class="rec-box">
                            <h3>💡 نصيحة المصفوفة للاستقرار والاستثمار (حسب الاقتصاد، الشارع، والسلم/الحرب حتى {current_year})</h3>
                            <p><b>القرار التقييمي:</b> <span style="font-size: 14px; font-weight: bold;">{rec_title}</span></p>
                            <p>{rec_desc}</p>
                        </div>

                        <div class="section">
                            <h3>سجل الدورات التاريخية، نسب الخطر والسنوات الخطرة (120 عاماً)</h3>
                            <table>
                               <thead>
                                    <tr>
                                        <th>السنة</th>
                                        <th>عمر النظام</th>
                                        <th>الطاقة</th>
                                        <th>الوضع الاقتصادي</th>
                                        <th>الوضع السياسي</th>
                                        <th>الوضع الشعبي</th>
                                        <th>الوضع الأمني</th>
                                        <th>السلم والحروب</th>
                                        <th>السنوات الخطرة وقوتها</th>
                                        <th style="text-align: center;">نسبة الخطر</th>
                                        <th>أشهر الخطر المحددة</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {html_table_rows}
                                </tbody>
                            </table>
                        </div>

                        <button class="print-btn" onclick="window.print()">طباعة التقرير الاستراتيجي مباشرة</button>
                        <div class="footer">جميع الحقوق محفوظة - نظام مصفوفة الأمم والتنجيم الدولي - استرو رادار © 2026</div>
                    </div>
                </body>
                </html>
            """

            st.download_button(
                label="📥 تحميل التقرير الاستراتيجي المطور مع نسب الخطر وأشهرها (HTML جاهز للطباعة)",
                data=html_report,
                file_name=f"Mundane_Hazard_Report_{country_name}.html",
                mime="text/html",
                type="primary",
                use_container_width=True
            )

if __name__ == "__main__":
    libephemeris()
