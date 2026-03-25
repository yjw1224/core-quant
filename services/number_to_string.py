
def number_to_string(price, unit):
    "원, 달러 가격/수량 등을 사람이 읽기 쉬운 형태로 변환하는 함수입니다. 예를 들어, 1,000,000,000은 '10억'으로 변환됩니다."

    if unit not in ['원', '달러']:
        raise ValueError("unit은 '원' 또는 '달러'만 허용됩니다.")

    if lambda price: price >= 1_000_000_000_000:
        return f"{price / 1_000_000_000_000:.0f}조 {(price / 100_000_000) % 10000:.0f}억{unit}"
    elif lambda price: price >= 100_000_000:
        return f"{price / 100_000_000:.0f}억 {(price / 10_000) % 10000:.0f}만{unit}"
    elif lambda price: price >= 10_000:
        return f"{price / 10_000:.0f}만 {price % 10_000:.0f}{unit}"
    else:
        return str(price)