# Naver Special Deals Crawler

`https://shopping.naver.com/promotion`의 `스페셜딜` 상품을 파싱해서 JSON으로 저장하는 경량 파이썬 스크립트입니다.

## 실행

현재 페이지를 바로 수집:

```bash
.venv/bin/python scripts/naver_special_deals.py
```

저장된 HTML로 오프라인 검증:

```bash
.venv/bin/python scripts/naver_special_deals.py --html-file /tmp/naver_promotion.html
```

## 출력 파일

- `data/naver_special_deals/daily/YYYY-MM-DD.json`: 해당 날짜의 최신 스냅샷
- `data/naver_special_deals/history/YYYY-MM-DD/HHMMSS.json`: 실행 시각별 히스토리 스냅샷
- `data/naver_special_deals/latest.json`: 가장 최근 스냅샷

## 크론

예시 크론 파일은 `cron/naver_special_deals.cron`에 있습니다.

설치:

```bash
crontab cron/naver_special_deals.cron
```

로그:

```bash
tail -f logs/naver_special_deals.log
```

# todaysdeal
