"""
Simple built-in country centroid lookup for map fallback.
Keys: ISO2 code or common country name uppercase -> (lat, lon)
This is a lightweight fallback; for production consider GeoNames or similar.
"""
import os

MAPPING = {
    'CN': (35.8617, 104.1954), 'CHINA': (35.8617, 104.1954),
    'US': (39.8283, -98.5795), 'UNITED STATES': (39.8283, -98.5795), 'USA': (39.8283, -98.5795),
    'JP': (36.2048, 138.2529), 'JAPAN': (36.2048, 138.2529),
    'DE': (51.1657, 10.4515), 'GERMANY': (51.1657, 10.4515),
    'FR': (46.2276, 2.2137), 'FRANCE': (46.2276, 2.2137),
    'GB': (55.3781, -3.4360), 'UK': (55.3781, -3.4360), 'UNITED KINGDOM': (55.3781, -3.4360),
    'CA': (56.1304, -106.3468), 'CANADA': (56.1304, -106.3468),
    'IN': (20.5937, 78.9629), 'INDIA': (20.5937, 78.9629),
    'AU': (-25.2744, 133.7751), 'AUSTRALIA': (-25.2744, 133.7751),
    'BR': (-14.2350, -51.9253), 'BRAZIL': (-14.2350, -51.9253),
    'RU': (61.5240, 105.3188), 'RUSSIA': (61.5240, 105.3188),
    'KR': (35.9078, 127.7669), 'SOUTH KOREA': (35.9078, 127.7669),
    'KR': (35.9078, 127.7669), 'KOREA': (35.9078, 127.7669),
    'SG': (1.3521, 103.8198), 'SINGAPORE': (1.3521, 103.8198),
    'NL': (52.1326, 5.2913), 'NETHERLANDS': (52.1326, 5.2913),
    'SE': (60.1282, 18.6435), 'SWEDEN': (60.1282, 18.6435),
    'NO': (60.4720, 8.4689), 'NORWAY': (60.4720, 8.4689),
    'ES': (40.4637, -3.7492), 'SPAIN': (40.4637, -3.7492),
    'IT': (41.8719, 12.5674), 'ITALY': (41.8719, 12.5674),
    'CH': (46.8182, 8.2275), 'SWITZERLAND': (46.8182, 8.2275),
    'BE': (50.5039, 4.4699), 'BELGIUM': (50.5039, 4.4699),
    'TR': (38.9637, 35.2433), 'TURKEY': (38.9637, 35.2433),
    'MX': (23.6345, -102.5528), 'MEXICO': (23.6345, -102.5528),
    'ZA': (-30.5595, 22.9375), 'SOUTH AFRICA': (-30.5595, 22.9375),
    'AR': (-38.4161, -63.6167), 'ARGENTINA': (-38.4161, -63.6167),
    'PL': (51.9194, 19.1451), 'POLAND': (51.9194, 19.1451),
    'ID': (-0.7893, 113.9213), 'INDONESIA': (-0.7893, 113.9213),
    'TH': (15.8700, 100.9925), 'THAILAND': (15.8700, 100.9925),
    'VN': (14.0583, 108.2772), 'VIETNAM': (14.0583, 108.2772),
    'PH': (12.8797, 121.7740), 'PHILIPPINES': (12.8797, 121.7740),
    'MY': (4.2105, 101.9758), 'MALAYSIA': (4.2105, 101.9758),
    'IL': (31.0461, 34.8516), 'ISRAEL': (31.0461, 34.8516),
    'SA': (23.8859, 45.0792), 'SAUDI ARABIA': (23.8859, 45.0792),
    'AE': (23.4241, 53.8478), 'UAE': (23.4241, 53.8478), 'UNITED ARAB EMIRATES': (23.4241, 53.8478),
}

def get_country_center(name):
    if not name:
        return (None, None)
    key = str(name).strip().upper()
    if key in MAPPING:
        return MAPPING[key]
    if len(key) >= 2 and key[:2] in MAPPING:
        return MAPPING[key[:2]]
    # optional GeoNames fallback when GEONAMES_USERNAME is set
    user = os.getenv('GEONAMES_USERNAME')
    if not user:
        return (None, None)
    # try to interpret key as ISO country code and call countryInfoJSON
    code = key[:2]
    try:
        import requests
        url = f'https://secure.geonames.org/countryInfoJSON?country={code}&username={user}'
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            j = r.json()
            gl = j.get('geonames') or []
            if gl:
                item = gl[0]
                # compute centroid from bounding box if available
                try:
                    north = float(item.get('north'))
                    south = float(item.get('south'))
                    east = float(item.get('east'))
                    west = float(item.get('west'))
                    lat = (north + south) / 2.0
                    lon = (east + west) / 2.0
                    return (lat, lon)
                except Exception:
                    pass
    except Exception:
        pass
    return (None, None)
