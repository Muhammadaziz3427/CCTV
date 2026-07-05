class ShelfMonitor:
    def __init__(self, shelves_config):
        # shelves_config = {"shelf_1": [x1, y1, x2, y2], ...}
        self.shelves = shelves_config

    def check_stock(self, frame):
        alerts = []
        for shelf_name, coords in self.shelves.items():
            # ROI kesib olish
            roi = frame[coords[1]:coords[3], coords[0]:coords[2]]
            # Agar mahsulotlar soni 0 ga yaqin bo'lsa
            if self._is_empty(roi):
                alerts.append(f"RESTOCK_REQUIRED: {shelf_name}")
        return alerts