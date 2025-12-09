from pymongo import MongoClient
import time

class Database:
    def __init__(self, uri="mongodb://localhost:27017/", db_name="mobile_robot"):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.collection = self.db["robot_data"]

    def insert_data(self, speed_data, direction, mode, gas_level=0, distance=0):
        """
        Lưu dữ liệu vào MongoDB.
        speed_data: Dictionary chứa tốc độ 4 bánh {'s1': 10, 's2': 12, ...}
        direction: Hướng di chuyển hiện tại
        mode: Chế độ (MANUAL/AUTO)
        gas_level: Giá trị cảm biến khí gas
        distance: Khoảng cách vật cản (cm)
        """
        document = {
            "timestamp": time.time(),
            "speed": speed_data,
            "direction": direction,
            "mode": mode,
            "gas": gas_level,
            "distance": distance
        }
        try:
            result = self.collection.insert_one(document)
            print(f"Data inserted with ID: {result.inserted_id}")
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error inserting data: {e}")
            return None

    def get_recent_data(self, limit=10):
        """Lấy dữ liệu gần đây nhất"""
        return list(self.collection.find().sort("timestamp", -1).limit(limit))
