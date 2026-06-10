import re
import asyncio
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from services.storage import (
    init_db, get_all_posts, get_stored_companies, get_all_analyses,
)
from services.intelligence import draft_counter_post

app = FastAPI(title="LinkedIn Analytics API")

# Enable CORS for Angular development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DB on startup
@app.on_event("startup")
def on_startup():
    init_db()

# Models
class DraftRequest(BaseModel):
    post_id: int
    company: str
    text: str

import time
from threading import Lock

_cache = {}
_cache_lock = Lock()
CACHE_TTL = 60 # seconds

# Helper to load data
def get_dashboard_data():
    now = time.time()
    with _cache_lock:
        if "dashboard" in _cache and now - _cache["dashboard"]["time"] < CACHE_TTL:
            return _cache["dashboard"]["data"]

    raw_posts = get_all_posts()
    raw_analyses = get_all_analyses()
    raw_companies = get_stored_companies()

    posts = [p.to_dict() for p in raw_posts]
    
    analyses = {}
    for post_id, a in raw_analyses.items():
        analyses[post_id] = {
            "executive_snapshot": a.executive_snapshot or "",
            "content_classification": a.content_classification or "",
            "strategic_intent": a.strategic_intent or "",
            "engagement_analysis": a.engagement_analysis or "",
            "creative_breakdown": a.creative_breakdown or "",
            "competitive_insight": a.competitive_insight or "",
            "recommended_action": a.recommended_action or "",
            "alert_tag": a.alert_tag or "LOW",
            "trend_signal": a.trend_signal or "",
        }

    result = (posts, analyses, raw_companies)
    
    with _cache_lock:
        _cache["dashboard"] = {"time": time.time(), "data": result}
        
    return result

@app.get("/api/companies")
def get_companies():
    _, _, companies = get_dashboard_data()
    return sorted(companies)

@app.get("/api/stats")
def get_stats():
    posts, analyses, _ = get_dashboard_data()
    
    high_count = 0
    med_count = 0
    low_count = 0
    total_eng = 0

    for p in posts:
        pid = p["id"]
        total_eng += p["engagement_score"]
        if pid in analyses:
            tag = analyses[pid].get("alert_tag", "LOW")
            if tag == "HIGH PRIORITY":
                high_count += 1
            elif tag == "MEDIUM":
                med_count += 1
            else:
                low_count += 1
                
    avg_eng = total_eng // len(posts) if posts else 0
    
    return {
        "high_priority": high_count,
        "medium": med_count,
        "low": low_count,
        "avg_engagement": avg_eng
    }

@app.get("/api/charts")
def get_charts():
    posts, analyses, _ = get_dashboard_data()
    
    # Avg Engagement by Company
    company_eng = {}
    company_counts = {}
    for p in posts:
        c = p["company"]
        company_eng[c] = company_eng.get(c, 0) + p["engagement_score"]
        company_counts[c] = company_counts.get(c, 0) + 1
        
    avg_eng_by_company = []
    for c, total in company_eng.items():
        avg = total / company_counts[c]
        avg_eng_by_company.append({"company": c, "avg_engagement": round(avg)})
        
    avg_eng_by_company.sort(key=lambda x: x["avg_engagement"])
    
    # Theme Breakdown
    theme_counts = {}
    for pid, a in analyses.items():
        cls = a.get("content_classification", "")
        if cls and cls != "UNKNOWN":
            primary = re.split(r'[/+]', cls)[0].strip()
            theme_counts[primary] = theme_counts.get(primary, 0) + 1
            
    sorted_themes = [{"theme": k, "count": v} for k, v in sorted(theme_counts.items(), key=lambda item: item[1], reverse=True)[:6]]
    
    return {
        "avg_eng_by_company": avg_eng_by_company,
        "themes": sorted_themes
    }

@app.get("/api/posts")
def get_feed(
    company: str = "All Companies",
    alert_level: str = "All Alerts",
    post_type: str = "All Types",
    days: Optional[int] = None
):
    posts, analyses, _ = get_dashboard_data()
    
    # Sort key logic
    def sort_key(p):
        a = analyses.get(p["id"], {})
        tag = a.get("alert_tag", "LOW")
        order = {"HIGH PRIORITY": 0, "MEDIUM": 1, "LOW": 2}
        return (order.get(tag, 2), -p["engagement_score"])
        
    sorted_posts = sorted(posts, key=sort_key)
    
    # Filter
    filtered = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    
    for p in sorted_posts:
        if company != "All Companies" and p["company"] != company:
            continue
            
        a = analyses.get(p["id"], {})
        if alert_level != "All Alerts" and a.get("alert_tag", "LOW") != alert_level:
            continue
            
        if post_type != "All Types" and p.get("post_type") != post_type:
            continue
            
        if cutoff and p.get("timestamp"):
            try:
                # Handle Z timezone offset
                ts_str = p["timestamp"].replace("Z", "+00:00")
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
            except ValueError:
                pass
                
        # Merge analysis into post
        p["analysis"] = a
        filtered.append(p)
        
    return filtered

@app.post("/api/draft-counter-post")
async def draft_post(request: DraftRequest):
    _, analyses, _ = get_dashboard_data()
    analysis = analyses.get(request.post_id)
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
        
    # Create simple namespace or dict for the draft_counter_post method
    class MockAnalysis:
        def __init__(self, d):
            for k, v in d.items():
                setattr(self, k, v)
                
    analysis_obj = MockAnalysis(analysis)
    post_dict = {"company": request.company, "text": request.text}
    
    try:
        draft = await draft_counter_post(post_dict, analysis_obj)
        return {"draft": draft}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
