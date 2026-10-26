"""로또 6/45 번호 생성기.

지금까지 나온 당첨번호를 모으고(수집), 패턴을 살펴보고(분석),
그 패턴에 맞춰 번호를 골라 준다(추천). 표준 라이브러리만 쓴다.

    python lotto.py              모으기 → 분석 → 추천 5줄 (한 번에)
    python lotto.py 수집          새로 나온 회차만 더 받아 오기
    python lotto.py 분석          패턴 보기
    python lotto.py 추천 10       추천 번호 10줄
    python lotto.py 검증          추천 방식이 실제로 맞았는지 지난 회차로 확인
    python lotto.py 가져오기 파일.csv   동행복권 엑셀을 CSV로 저장한 파일 넣기

로또 추첨은 매번 독립된 무작위다. 지난 번호의 패턴은 다음 번호를 맞힐 확률을
올려 주지 않는다. 이 프로그램은 '흔히 나오는 모양'에 맞춘 번호를 골라 줄 뿐이고,
'검증'을 돌려 보면 그냥 아무 번호와 비슷하게 맞는다는 걸 직접 볼 수 있다.
"""

import csv
import json
import math
import os
import random
import sys
import urllib.request
from collections import Counter
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(HERE, "lotto_data.json")
SOURCE = "https://smok95.github.io/lotto/results/all.json"
NUMBERS = range(1, 46)
RECENT = 50  # '최근'으로 보는 회차 수


# ---------------------------------------------------------------- 수집

def load():
    """저장된 회차들. [{"회차": 1, "날짜": "2002-12-07", "번호": [..6개], "보너스": n}, ...]"""
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def save(draws):
    draws = sorted({d["회차"]: d for d in draws}.values(), key=lambda d: d["회차"])
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        f.write("[\n" + ",\n".join(json.dumps(d, ensure_ascii=False) for d in draws) + "\n]\n")  # 한 줄에 한 회차
    return draws


def fetch_all():
    """회차별 당첨번호 전체를 받아 온다. 동행복권의 예전 조회 주소가 없어져서,
    매주 당첨번호를 정리해 공개하는 smok95/lotto(https://github.com/smok95/lotto)를 쓴다."""
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    draws = []
    for x in data:
        nums = sorted(x["numbers"])
        if len(set(nums)) == 6 and all(1 <= n <= 45 for n in nums):
            draws.append({"회차": x["draw_no"], "날짜": x["date"][:10], "번호": nums, "보너스": x["bonus_no"]})
    return draws


def collect():
    draws = load()
    last = draws[-1]["회차"] if draws else 0
    print("당첨번호 받아 오는 중...")
    try:
        new = [d for d in fetch_all() if d["회차"] > last]
    except Exception as e:  # 인터넷 끊김, 사이트 바뀜 등
        print(f"  받지 못했다: {e}")
        print("  인터넷을 확인하거나, 동행복권 '회차별 당첨번호' 엑셀을 CSV로 저장해서")
        print("  python lotto.py 가져오기 파일.csv 로 넣어도 된다.")
        return draws
    draws = save(draws + new)
    if draws:
        print(f"새로 {len(new)}회 추가. 모두 {len(draws)}회 (마지막 {draws[-1]['회차']}회 {draws[-1]['날짜']})")
    return draws


def import_csv(path):
    """동행복권 엑셀을 CSV로 저장한 파일 등. 한 줄에 회차 하나.
    줄 안의 숫자 중 1~45 사이 연속 7개(번호 6 + 보너스)를 찾고, 첫 숫자를 회차로 본다."""
    draws = load()
    added = 0
    for enc in ("utf-8-sig", "cp949"):
        try:
            with open(path, encoding=enc, newline="") as f:
                rows = list(csv.reader(f))
            break
        except UnicodeDecodeError:
            continue
    for row in rows:
        nums = [int(c.replace(",", "")) for c in row if c.strip().replace(",", "").isdigit()]
        if len(nums) < 8:
            continue
        for i in range(1, len(nums) - 6):
            seven = nums[i:i + 7]
            if all(1 <= n <= 45 for n in seven) and len(set(seven)) == 7:
                draws.append({"회차": nums[0], "날짜": "", "번호": sorted(seven[:6]), "보너스": seven[6]})
                added += 1
                break
    draws = save(draws)
    print(f"{added}줄 읽음. 모두 {len(draws)}회")


# ---------------------------------------------------------------- 분석

def gaps(draws):
    """번호마다 마지막으로 나온 뒤 몇 회째 안 나왔는지."""
    last = {}
    for i, d in enumerate(draws):
        for n in d["번호"]:
            last[n] = i
    return {n: len(draws) - 1 - last.get(n, -1) for n in NUMBERS}


def shape(nums):
    """한 줄의 모양: 합, 홀수 개수, 낮은 번호(1~22) 개수, 이어진 짝 수, 같은 끝자리 최대 개수."""
    nums = sorted(nums)
    return {
        "합": sum(nums),
        "홀": sum(n % 2 for n in nums),
        "저": sum(n <= 22 for n in nums),
        "연속": sum(b - a == 1 for a, b in zip(nums, nums[1:])),
        "끝수": max(Counter(n % 10 for n in nums).values()),
        "구간": max(Counter((n - 1) // 10 for n in nums).values()),
    }


def percentile(values, p):
    values = sorted(values)
    k = (len(values) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def chi_square(draws):
    """번호별 출현 횟수가 고르게 나온 것과 얼마나 다른지 (카이제곱, 자유도 44).
    자유도 44에서 유의수준 5% 경계는 약 60.5."""
    cnt = Counter(n for d in draws for n in d["번호"])
    expected = len(draws) * 6 / 45
    return sum((cnt[n] - expected) ** 2 / expected for n in NUMBERS)


def bar(v, vmax, width=20):
    return "█" * round(v / vmax * width) if vmax else ""


def analyze(draws):
    if not draws:
        print("데이터가 없다. 먼저 python lotto.py 수집")
        return
    total = len(draws)
    allcnt = Counter(n for d in draws for n in d["번호"])
    recent = draws[-RECENT:]
    reccnt = Counter(n for d in recent for n in d["번호"])
    gap = gaps(draws)

    print(f"\n===== {draws[0]['회차']}회 ~ {draws[-1]['회차']}회, 모두 {total}회 =====")

    print("\n[번호별 나온 횟수]  (고르게 나왔다면 번호마다 약 {:.0f}번)".format(total * 6 / 45))
    vmax = max(allcnt.values())
    for n in NUMBERS:
        print(f"  {n:2d} {allcnt[n]:4d} {bar(allcnt[n], vmax)}  최근{RECENT}회 {reccnt[n]}번, {gap[n]}회째 안 나옴")

    top = [n for n, _ in allcnt.most_common(10)]
    low = [n for n, _ in sorted(allcnt.items(), key=lambda x: x[1])[:10]]
    hot = [n for n, _ in reccnt.most_common(10)]
    cold = sorted(NUMBERS, key=lambda n: -gap[n])[:10]
    print(f"\n  가장 많이 나온 번호   {top}")
    print(f"  가장 적게 나온 번호   {low}")
    print(f"  최근 {RECENT}회에 많이 나온 {hot}")
    print(f"  오래 안 나온 번호     {cold}")

    chi = chi_square(draws)
    print(f"\n[고르게 나왔나?] 카이제곱 {chi:.1f} (60.5를 넘으면 '치우침'이 통계적으로 의심됨)")
    print("  → " + ("치우침이 보인다. 그래도 우연일 수 있다." if chi > 60.5
                    else "완전히 무작위로 뽑았을 때와 구별되지 않는다. 즉 특별히 잘 나오는 번호는 없다."))

    shapes = [shape(d["번호"]) for d in draws]

    def dist(key, label):
        c = Counter(s[key] for s in shapes)
        parts = ", ".join(f"{k}{label}:{v / total:.0%}" for k, v in sorted(c.items()))
        return parts

    sums = [s["합"] for s in shapes]
    print("\n[한 줄의 모양]")
    print(f"  합계        평균 {sum(sums) / total:.0f}, 가운데 80%는 {percentile(sums, .1):.0f} ~ {percentile(sums, .9):.0f}")
    print(f"  홀수 개수   {dist('홀', '개')}")
    print(f"  1~22 개수   {dist('저', '개')}")
    print(f"  이어진 짝   {dist('연속', '쌍')}")
    print(f"  같은 끝자리 {dist('끝수', '개')}")
    print(f"  같은 10단위 {dist('구간', '개')}")

    pairs = Counter(p for d in draws for p in combinations(d["번호"], 2))
    print("\n[같이 자주 나온 두 번호]")
    print("  " + ", ".join(f"{a}-{b}({c}번)" for (a, b), c in pairs.most_common(10)))

    if len(draws) >= 2:
        repeat = [len(set(a["번호"]) & set(b["번호"])) for a, b in zip(draws, draws[1:])]
        print(f"\n[바로 전 회차 번호가 또 나온 개수] 평균 {sum(repeat) / len(repeat):.2f}개 "
              f"(무작위면 0.80개), 0개:{repeat.count(0) / len(repeat):.0%}")


# ---------------------------------------------------------------- 추천

def build_filter(draws):
    """지난 당첨번호 대부분(가운데 80% 정도)이 가진 모양을 조건으로 만든다."""
    shapes = [shape(d["번호"]) for d in draws]
    sums = [s["합"] for s in shapes]
    lo, hi = percentile(sums, .1), percentile(sums, .9)
    past = {tuple(d["번호"]) for d in draws}

    def ok(nums):
        s = shape(nums)
        return (lo <= s["합"] <= hi and 2 <= s["홀"] <= 4 and 2 <= s["저"] <= 4
                and s["연속"] <= 1 and s["끝수"] <= 2 and s["구간"] <= 3
                and tuple(sorted(nums)) not in past)

    return ok


def weights(draws):
    """번호마다 뽑힐 무게. 전체 횟수 + 최근 횟수 + 오래 안 나온 정도를 섞는다.
    모두 1 근처로 눌러서 어느 번호도 너무 몰리지 않게 한다."""
    total = len(draws)
    allcnt = Counter(n for d in draws for n in d["번호"])
    recent = draws[-RECENT:]
    reccnt = Counter(n for d in recent for n in d["번호"])
    gap = gaps(draws)
    exp_all = total * 6 / 45
    exp_rec = len(recent) * 6 / 45
    w = {}
    for n in NUMBERS:
        a = allcnt[n] / exp_all if exp_all else 1
        r = reccnt[n] / exp_rec if exp_rec else 1
        g = min(gap[n] / 7.5, 3)  # 평균 7.5회마다 한 번 나온다
        w[n] = 0.4 * a + 0.4 * r + 0.2 * g + 0.2
    return w


def pick(w, ok, rng, tries=10000):
    nums, ws = list(w), list(w.values())
    for _ in range(tries):
        chosen = set()
        while len(chosen) < 6:
            chosen.add(rng.choices(nums, ws)[0])
        if ok(chosen):
            return sorted(chosen)
    return sorted(rng.sample(nums, 6))


def recommend(draws, count=5, seed=None):
    if not draws:
        print("데이터가 없다. 먼저 python lotto.py 수집")
        return []
    rng = random.Random(seed)
    ok = build_filter(draws)
    w = weights(draws)
    lines = []
    while len(lines) < count:
        line = pick(w, ok, rng)
        if line not in lines:
            lines.append(line)
    print(f"\n===== {draws[-1]['회차'] + 1}회 추천 번호 =====")
    for i, line in enumerate(lines):
        s = shape(line)
        print(f"  {chr(65 + i) if i < 26 else i + 1}  " + " ".join(f"{n:2d}" for n in line)
              + f"    합 {s['합']}, 홀{s['홀']}:짝{6 - s['홀']}, 낮은{s['저']}:높은{6 - s['저']}")
    print("\n  (패턴에 맞춘 번호일 뿐 당첨 확률은 아무 번호와 같다: 1등 1/8,145,060)")
    return lines


# ---------------------------------------------------------------- 검증

PRIZE = {6: "1등", 5: "3등", 4: "4등", 3: "5등"}


def backtest(draws, test=100, lines=5, seed=1):
    """지난 test회 각각에 대해 그 전까지의 데이터만 보고 추천해 보고, 실제 번호와 맞춰 본다.
    같은 수의 아무 번호(완전 무작위)와 비교한다."""
    if len(draws) < test + 100:
        test = max(0, len(draws) - 100)
    if test == 0:
        print("검증하려면 적어도 101회 데이터가 필요하다.")
        return
    rng = random.Random(seed)
    mine, rand = Counter(), Counter()
    for i in range(len(draws) - test, len(draws)):
        past, real = draws[:i], set(draws[i]["번호"])
        ok, w = build_filter(past), weights(past)
        for _ in range(lines):
            mine[len(real & set(pick(w, ok, rng)))] += 1
            rand[len(real & set(rng.sample(range(1, 46), 6)))] += 1
    n = test * lines
    print(f"\n===== 지난 {test}회, 회차마다 {lines}줄씩 ({n}줄) =====")
    print("  맞은 개수    추천 방식      아무 번호     (이론값)")
    for k in range(7):
        theory = math.comb(6, k) * math.comb(39, 6 - k) / math.comb(45, 6)
        print(f"  {k}개 {PRIZE.get(k, ''):3s}   {mine[k]:5d} ({mine[k] / n:6.2%})  "
              f"{rand[k]:5d} ({rand[k] / n:6.2%})  ({theory:6.2%})")
    avg_m = sum(k * v for k, v in mine.items()) / n
    avg_r = sum(k * v for k, v in rand.items()) / n
    print(f"  평균 맞은 개수  추천 {avg_m:.3f}개 / 아무 번호 {avg_r:.3f}개 / 이론 0.800개")
    print("  → 차이가 0.05개 안쪽이면 그냥 운의 차이다.")


# ---------------------------------------------------------------- 실행

def main(args):
    cmd = args[0] if args else "전부"
    if cmd in ("수집", "update"):
        collect()
    elif cmd in ("분석", "analyze"):
        analyze(load())
    elif cmd in ("추천", "pick"):
        recommend(load(), int(args[1]) if len(args) > 1 else 5)
    elif cmd in ("검증", "test"):
        backtest(load(), int(args[1]) if len(args) > 1 else 100)
    elif cmd in ("가져오기", "import") and len(args) > 1:
        import_csv(args[1])
    elif cmd == "전부":
        draws = collect()
        analyze(draws)
        recommend(draws)
    else:
        print(__doc__)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서 한글 깨짐 막기
    main(sys.argv[1:])
