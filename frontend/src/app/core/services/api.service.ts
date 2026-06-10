import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Post {
  id: number;
  company: string;
  text: string;
  post_type: string;
  timestamp: string;
  likes: number;
  comments: number;
  shares: number;
  engagement_score: number;
  engagement_rate: number;
  reactions: any;
  hashtags: string[];
  media_description: string;
  post_url: string;
  post_urn: string;
  media_urls: string[];
  follower_count: number;
  is_repost: boolean;
  is_edited: boolean;
  author_name: string;
  analysis?: any;
}

export interface Stats {
  high_priority: number;
  medium: number;
  low: number;
  avg_engagement: number;
}

export interface Charts {
  avg_eng_by_company: { company: string, avg_engagement: number }[];
  themes: { theme: string, count: number }[];
}

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private apiUrl = 'http://localhost:8080/api';

  constructor(private http: HttpClient) { }

  getCompanies(): Observable<string[]> {
    return this.http.get<string[]>(`${this.apiUrl}/companies`);
  }

  getStats(): Observable<Stats> {
    return this.http.get<Stats>(`${this.apiUrl}/stats`);
  }

  getCharts(): Observable<Charts> {
    return this.http.get<Charts>(`${this.apiUrl}/charts`);
  }

  getPosts(company: string, alertLevel: string, postType: string, days?: number): Observable<Post[]> {
    let params = new HttpParams()
      .set('company', company)
      .set('alert_level', alertLevel)
      .set('post_type', postType);
    
    if (days) {
      params = params.set('days', days.toString());
    }

    return this.http.get<Post[]>(`${this.apiUrl}/posts`, { params });
  }

  draftCounterPost(postId: number, company: string, text: string): Observable<{draft: string}> {
    return this.http.post<{draft: string}>(`${this.apiUrl}/draft-counter-post`, {
      post_id: postId,
      company: company,
      text: text
    });
  }
}
