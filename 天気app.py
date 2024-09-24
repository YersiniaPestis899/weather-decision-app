import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import googlemaps
import pandas as pd
import folium
from streamlit_folium import folium_static
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# API keys and endpoints
OPENWEATHERMAP_API_KEY = st.secrets["OPENWEATHER_API_KEY"]
GOOGLE_MAPS_API_KEY = st.secrets["GOOGLE_MAPS_API_KEY"]

# Initialize Google Maps client
gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

def get_weather(latitude, longitude):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={OPENWEATHERMAP_API_KEY}&units=metric&lang=ja"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"現在の天気情報の取得中にエラーが発生しました: {str(e)}")
        st.error(f"URL: {url.replace(OPENWEATHERMAP_API_KEY, 'API_KEY')}")
        st.error(f"Response: {response.text if 'response' in locals() else 'No response'}")
        return None

def get_weather_forecast(latitude, longitude):
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={latitude}&lon={longitude}&appid={OPENWEATHERMAP_API_KEY}&units=metric&lang=ja"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"天気予報の取得中にエラーが発生しました: {str(e)}")
        st.error(f"URL: {url.replace(OPENWEATHERMAP_API_KEY, 'API_KEY')}")
        st.error(f"Response: {response.text if 'response' in locals() else 'No response'}")
        return None

def get_coordinates(address):
    result = gmaps.geocode(address)
    if result:
        location = result[0]['geometry']['location']
        return (location['lat'], location['lng'])
    else:
        raise ValueError(f"住所が見つかりませんでした: {address}")

def get_travel_info(origin, destination):
    now = datetime.now()
    directions_result = gmaps.directions(origin, destination, mode="driving", departure_time=now)
    if directions_result:
        leg = directions_result[0]['legs'][0]
        return {
            'distance': leg['distance']['text'],
            'duration': leg['duration']['text'],
            'duration_in_traffic': leg['duration_in_traffic']['text']
        }
    else:
        raise ValueError(f"経路が見つかりませんでした: {origin} から {destination}")

def analyze_outing(weather_data, forecast_data, travel_info, purpose, additional_question):
    if weather_data is None or forecast_data is None:
        return "天気情報の取得に失敗したため、外出判断を行えません。"

    forecast_summary = process_forecast_data(forecast_data)
    forecast_text = forecast_summary.to_string(index=False)

    analysis = f"""
    外出目的: {purpose}

    現在の天気情報:
    - 天気: {weather_data['weather'][0]['description']}
    - 気温: {weather_data['main']['temp']}°C
    - 湿度: {weather_data['main']['humidity']}%
    - 風速: {weather_data['wind']['speed']} m/s

    5日間の天気予報:
    {forecast_text}

    移動情報:
    - 移動距離: {travel_info['distance']}
    - 通常の所要時間: {travel_info['duration']}
    - 交通状況を考慮した所要時間: {travel_info['duration_in_traffic']}

    分析:
    1. 今日の外出について:
       現在の天気と目的を考慮すると、{"今日の外出は適していると思われます。" if weather_data['weather'][0]['id'] < 800 else "今日の外出は天候の影響を受ける可能性があります。"}

    2. 最適な外出日:
       5日間の予報を見ると、{forecast_summary.iloc[forecast_summary['天気'].str.contains('晴れ|曇り').idxmax()]['日付']}が最も外出に適していると思われます。

    3. 天候の影響:
       {purpose}という目的に対して、現在および今後の天候は{"好影響を与えると予想されます。" if '晴れ' in weather_data['weather'][0]['description'] else "注意が必要かもしれません。"}

    4. 外出のタイミング:
       移動時間と交通状況を考慮すると、{travel_info['duration_in_traffic']}かかる予定です。混雑を避けるため、早朝か夕方以降の外出をお勧めします。

    追加の回答: {additional_question}
    {additional_question if additional_question else "追加の質問がありませんでした。"}
    """

    return analysis

def process_forecast_data(forecast_data):
    processed_data = []
    current_date = datetime.now().date()
    for item in forecast_data['list']:
        date = datetime.fromtimestamp(item['dt'])
        if date.date() > current_date and len(processed_data) < 5:  # 今日を除く5日分のデータを取得
            if date.hour == 12:  # 正午のデータのみを使用
                processed_data.append({
                    '日付': date.strftime('%Y-%m-%d'),
                    '天気': item['weather'][0]['description'],
                    '気温': f"{item['main']['temp']:.1f}°C",
                    '湿度': f"{item['main']['humidity']}%",
                    '風速': f"{item['wind']['speed']} m/s"
                })
    return pd.DataFrame(processed_data)

def create_map(start_coords, end_coords):
    center_lat = (start_coords[0] + end_coords[0]) / 2
    center_lng = (start_coords[1] + end_coords[1]) / 2
    
    m = folium.Map(location=[center_lat, center_lng], zoom_start=6)
    
    folium.Marker(
        start_coords,
        popup="出発地",
        icon=folium.Icon(color="red", icon="info-sign"),
    ).add_to(m)
    
    folium.Marker(
        end_coords,
        popup="目的地",
        icon=folium.Icon(color="green", icon="info-sign"),
    ).add_to(m)
    
    folium.PolyLine(
        locations=[start_coords, end_coords],
        color="blue",
        weight=2,
        opacity=0.8
    ).add_to(m)
    
    return m

def main():
    st.set_page_config(page_title="外出判断アプリ", page_icon="🏙️", layout="wide")

    st.title("🏠🚗 外出判断アプリ")
    st.write("天気と交通情報に基づいて、目的地に行くべきかどうかを判断します。")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📍 場所情報")
        start_location = st.text_input("出発地", "")
        end_location = st.text_input("目的地", "")
        purpose = st.text_input("外出の目的（例：買い物、観光、ビジネス）", "")
        additional_question = st.text_input("追加の質問（オプション）", "")

    if st.button("外出判断を実行", key="run_analysis"):
        with st.spinner("分析中..."):
            try:
                start_coords = get_coordinates(start_location)
                end_coords = get_coordinates(end_location)
                weather_data = get_weather(start_coords[0], start_coords[1])
                forecast_data = get_weather_forecast(start_coords[0], start_coords[1])
                travel_info = get_travel_info(start_location, end_location)

                if weather_data is None or forecast_data is None:
                    st.error("天気情報の取得に失敗しました。APIキーを確認してください。")
                    return

                with col2:
                    st.subheader("🗺️ 位置情報")
                    map = create_map(start_coords, end_coords)
                    folium_static(map)

                st.subheader("🌤️ 現在の天気情報")
                weather_col1, weather_col2 = st.columns(2)
                with weather_col1:
                    st.metric("天気", weather_data['weather'][0]['description'])
                    st.metric("気温", f"{weather_data['main']['temp']}°C")
                with weather_col2:
                    st.metric("湿度", f"{weather_data['main']['humidity']}%")
                    st.metric("風速", f"{weather_data['wind']['speed']} m/s")

                st.subheader("📅 5日間の天気予報")
                forecast_df = process_forecast_data(forecast_data)
                st.dataframe(forecast_df, hide_index=True)

                st.subheader("🚗 移動情報")
                travel_col1, travel_col2, travel_col3 = st.columns(3)
                with travel_col1:
                    st.metric("距離", travel_info['distance'])
                with travel_col2:
                    st.metric("通常の所要時間", travel_info['duration'])
                with travel_col3:
                    st.metric("交通状況考慮時間", travel_info['duration_in_traffic'])

                recommendation = analyze_outing(weather_data, forecast_data, travel_info, purpose, additional_question)

                st.subheader("🤖 AIによる外出判断")
                st.info(recommendation)

            except Exception as e:
                st.error(f"エラーが発生しました: {str(e)}")

if __name__ == "__main__":
    main()