import streamlit as st
import requests
import json
from datetime import datetime
import boto3
import googlemaps
import pandas as pd
import folium
from streamlit_folium import folium_static
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# API keys
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

def initialize_gmaps(api_key):
    return googlemaps.Client(key=api_key)

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

def get_weather(api_key, latitude, longitude):
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={api_key}&units=metric&lang=ja"
    response = requests.get(url)
    return response.json()

def get_weather_forecast(api_key, latitude, longitude):
    url = f"http://api.openweathermap.org/data/2.5/forecast?lat={latitude}&lon={longitude}&appid={api_key}&units=metric&lang=ja"
    response = requests.get(url)
    return response.json()

def get_coordinates(gmaps, address):
    result = gmaps.geocode(address)
    if result:
        location = result[0]['geometry']['location']
        return (location['lat'], location['lng'])
    else:
        raise ValueError(f"住所が見つかりませんでした: {address}")

def get_travel_info(gmaps, origin, destination):
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

def process_forecast_data(forecast_data):
    processed_data = []
    for item in forecast_data['list']:
        date = datetime.fromtimestamp(item['dt'])
        if date.hour == 12:  # 正午のデータのみを使用
            processed_data.append({
                '日付': date.strftime('%Y-%m-%d'),
                '天気': item['weather'][0]['description'],
                '気温': f"{item['main']['temp']:.1f}°C",
                '湿度': f"{item['main']['humidity']}%",
                '風速': f"{item['wind']['speed']} m/s"
            })
    return pd.DataFrame(processed_data)

def analyze_outing(bedrock_client, weather_data, forecast_data, travel_info, purpose, additional_question):
    forecast_summary = process_forecast_data(forecast_data)
    forecast_text = forecast_summary.to_string(index=False)

    user_message = f"""
    あなたは外出判断のアシスタントです。以下の情報に基づいて、目的地に行くべきか、行かないべきかを判断し、理由とともに回答してください。

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

    以下の質問に具体的に答えてください：
    1. 目的地に今日行くべきでしょうか？それとも別の日に行くべきでしょうか？理由も説明してください。
    2. もし別の日に行くべきだと判断した場合、5日間の予報の中でどの日が最適だと思われますか？その理由も説明してください。
    3. 外出目的を達成するのに、現在および今後の天候はどのような影響を与えると予想されますか？具体的に説明してください。
    4. 移動時間や交通状況を考慮すると、外出のタイミングについて何か助言はありますか？詳しく説明してください。

    追加の質問: {additional_question}
    この追加の質問にも、APIから取得した情報を引用し具体的かつ詳細に答えてください。

    回答は各質問に対して明確に分けて、簡潔にまとめてください。
    """

    messages = [
        {
            "role": "user",
            "content": user_message
        }
    ]

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 200000,
        "messages": messages,
        "temperature": 0.5,
        "top_p": 0.9,
    })

    try:
        response = bedrock_client.invoke_model(
            modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
            contentType="application/json",
            accept="application/json",
            body=body
        )
        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']
    except Exception as e:
        return f"AIの分析中にエラーが発生しました: {str(e)}"

def main():
    st.set_page_config(page_title="外出判断アプリ", page_icon="🏙️", layout="wide")

    st.title("🏠🚗 外出判断アプリ")
    st.write("天気と交通情報に基づいて、目的地に行くべきかどうかを判断します。")

    # API key inputs
    st.sidebar.header("API Keys")
    openweathermap_api_key = st.sidebar.text_input("OpenWeatherMap API Key", value=OPENWEATHERMAP_API_KEY or "", type="password")
    google_maps_api_key = st.sidebar.text_input("Google Maps API Key", value=GOOGLE_MAPS_API_KEY or "", type="password")

    # AWS認証情報の入力
    st.sidebar.header("AWS認証情報")
    aws_access_key_id = st.sidebar.text_input("AWS Access Key ID", type="password")
    aws_secret_access_key = st.sidebar.text_input("AWS Secret Access Key", type="password")
    aws_region = st.sidebar.text_input("AWSリージョン", value="")

    st.sidebar.warning("注意: APIやAWS認証情報は慎重に扱ってください。この情報を他人と共有しないでください。")

    # 入力チェック
    if not google_maps_api_key:
        st.error("Google Maps API Keyを入力してください。")
        return

    if not openweathermap_api_key:
        st.error("OpenWeatherMap API Keyを入力してください。")
        return

    # Google Maps clientの初期化
    try:
        gmaps = initialize_gmaps(google_maps_api_key)
    except ValueError as e:
        st.error(f"Google Maps clientの初期化に失敗しました: {str(e)}")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📍 場所情報")
        start_location = st.text_input("出発地", "")
        end_location = st.text_input("目的地", "")
        purpose = st.text_input("外出の目的（例：買い物、観光、ビジネス）", "")
        additional_question = st.text_input("追加の質問（オプション）", "")

    if st.button("外出判断を実行", key="run_analysis"):
        if not (aws_access_key_id and aws_secret_access_key):
            st.error("AWS認証情報（Access Key IDとSecret Access Key）を入力してください。")
        elif not (start_location and end_location and purpose):
            st.error("出発地、目的地、外出の目的を入力してください。")
        else:
            with st.spinner("分析中..."):
                try:
                    # AWS認証情報を使用してBedrockクライアントを初期化
                    bedrock_client = boto3.client('bedrock-runtime', 
                                                  region_name=aws_region,
                                                  aws_access_key_id=aws_access_key_id,
                                                  aws_secret_access_key=aws_secret_access_key)

                    start_coords = get_coordinates(gmaps, start_location)
                    end_coords = get_coordinates(gmaps, end_location)
                    weather_data = get_weather(openweathermap_api_key, start_coords[0], start_coords[1])
                    forecast_data = get_weather_forecast(openweathermap_api_key, start_coords[0], start_coords[1])
                    travel_info = get_travel_info(gmaps, start_location, end_location)

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
                    forecast_df = forecast_df.reset_index(drop=True)
                    st.dataframe(forecast_df)

                    st.subheader("🚗 移動情報")
                    travel_col1, travel_col2, travel_col3 = st.columns(3)
                    with travel_col1:
                        st.metric("距離", travel_info['distance'])
                    with travel_col2:
                        st.metric("通常の所要時間", travel_info['duration'])
                    with travel_col3:
                        st.metric("交通状況考慮時間", travel_info['duration_in_traffic'])

                    recommendation = analyze_outing(bedrock_client, weather_data, forecast_data, travel_info, purpose, additional_question)

                    st.subheader("🤖 AIによる外出判断")
                    st.markdown(recommendation)

                except Exception as e:
                    st.error(f"エラーが発生しました: {str(e)}")

if __name__ == "__main__":
    main()