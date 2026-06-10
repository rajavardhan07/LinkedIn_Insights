import { Component, OnInit, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, Post, Stats, Charts } from './core/services/api.service';
import Chart from 'chart.js/auto';
import ChartDataLabels from 'chartjs-plugin-datalabels';
import { marked } from 'marked';

Chart.register(ChartDataLabels);

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit {
  stats: Stats | null = null;
  charts: Charts | null = null;
  companies: string[] = [];
  posts: Post[] = [];
  
  // Download Filters
  dlCompany = 'All Companies';
  dlFilterMode = 'Past N posts';
  dlPostsLimit: number | string = 50;
  dlDaysLimit: number = 30;

  dlPostOptions = [10, 25, 50, 100, 250, 'All'];
  dlDaysOptions = [7, 14, 30, 60, 90, 180];

  // Feed Filters
  feedCompany = 'All Companies';
  feedAlert = 'All Alerts';
  feedType = 'All Types';
  feedDays = 'Last 7 days';
  
  feedDaysMap: {[key: string]: number | undefined} = {
    'All Time': undefined,
    'Last 7 days': 7,
    'Last 14 days': 14,
    'Last 30 days': 30,
    'Last 90 days': 90
  };
  
  feedDaysOptions = Object.keys(this.feedDaysMap);
  feedTypes = ['All Types'];

  feedCurrentPage = 1;
  feedPageSize = 5;
  Math = Math;

  isGeneratingDraft: { [key: number]: boolean } = {};
  generatedDrafts: { [key: number]: string } = {};
  
  currentDate = new Date();

  @ViewChild('barChart') barChartRef!: ElementRef;
  @ViewChild('pieChart') pieChartRef!: ElementRef;
  
  barChart: any;
  pieChart: any;
  
  pieColors = ["#7C5CFC", "#5B8AF0", "#10B981", "#EF4444", "#F59E0B", "#8892A8", "#F472B6", "#38BDF8"];

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getStats().subscribe(res => this.stats = res);
    this.api.getCompanies().subscribe(res => {
      this.companies = ['All Companies', ...res];
    });
    this.api.getCharts().subscribe(res => {
      this.charts = res;
      setTimeout(() => this.initCharts(), 100);
    });
    this.loadFeed();
  }

  initCharts() {
    if (!this.charts) return;

    // Bar Chart
    if (this.barChartRef && !this.barChart) {
      const colors = ['#1C2234', '#222A40', '#304169', '#4668B8', '#5B8AF0', '#7C5CFC'];
      
      this.barChart = new Chart(this.barChartRef.nativeElement, {
        type: 'bar',
        data: {
          labels: this.charts.avg_eng_by_company.map(c => c.company),
          datasets: [{
            data: this.charts.avg_eng_by_company.map(c => c.avg_engagement),
            backgroundColor: colors.reverse(),
            borderRadius: 2
          }]
        },
        options: {
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          layout: { padding: { right: 30 } },
          plugins: { 
            legend: { display: false },
            tooltip: { backgroundColor: '#1C2234', titleColor: '#E2E8F0', bodyColor: '#8892A8' },
            datalabels: {
              anchor: 'end',
              align: 'right',
              color: '#8892A8',
              font: { size: 11, family: 'system-ui' }
            }
          },
          scales: {
            x: { display: false, grid: { display: false } },
            y: { 
              grid: { display: false }, 
              ticks: { color: '#CBD5E1', font: { size: 12, family: 'system-ui' } },
              border: { display: false }
            }
          }
        }
      });
    }

    // Pie Chart
    if (this.pieChartRef && !this.pieChart) {
      
      this.pieChart = new Chart(this.pieChartRef.nativeElement, {
        type: 'doughnut',
        data: {
          labels: this.charts.themes.map(t => t.theme),
          datasets: [{
            data: this.charts.themes.map(t => t.count),
            backgroundColor: this.pieColors,
            borderColor: '#0F1423',
            borderWidth: 2
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '60%',
          plugins: {
            legend: { display: false },
            tooltip: { backgroundColor: '#1C2234', titleColor: '#E2E8F0', bodyColor: '#8892A8' },
            datalabels: {
              color: '#1C2234',
              font: { size: 11, weight: 'bold', family: 'system-ui' },
              formatter: (value, ctx) => {
                let sum = 0;
                let dataArr = ctx.chart.data.datasets[0].data;
                dataArr.map((data: any) => sum += Number(data));
                let pct = (Number(value) * 100 / sum).toFixed(0);
                if (Number(pct) < 4) return ''; // Hide if too small
                return pct + "%";
              }
            }
          }
        }
      });
    }
  }

  loadFeed() {
    const days = this.feedDaysMap[this.feedDays];
    this.api.getPosts(this.feedCompany, this.feedAlert, this.feedType, days).subscribe(res => {
      this.posts = res.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      this.feedCurrentPage = 1;
      
      // Extract unique types for dropdown
      const types = new Set(this.posts.map(p => p.post_type).filter(t => t));
      this.feedTypes = ['All Types', ...Array.from(types)] as string[];
    });
  }

  get paginatedPosts() {
    const start = (this.feedCurrentPage - 1) * this.feedPageSize;
    return this.posts.slice(start, start + this.feedPageSize);
  }

  get totalPages() {
    return Math.ceil(this.posts.length / this.feedPageSize) || 1;
  }

  nextPage() {
    if (this.feedCurrentPage < this.totalPages) this.feedCurrentPage++;
  }

  prevPage() {
    if (this.feedCurrentPage > 1) this.feedCurrentPage--;
  }

  get filteredDownloadPosts() {
    let pool = [...this.posts];
    if (this.dlCompany !== 'All Companies') {
      pool = pool.filter(p => p.company === this.dlCompany);
    }
    
    if (this.dlFilterMode === 'Past N posts') {
      if (this.dlPostsLimit !== 'All' as any) {
        pool = pool.slice(0, this.dlPostsLimit as number);
      }
    } else {
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - this.dlDaysLimit);
      pool = pool.filter(p => new Date(p.timestamp) >= cutoff);
    }
    return pool;
  }

  draftCounterPost(post: Post) {
    this.isGeneratingDraft[post.id] = true;
    this.api.draftCounterPost(post.id, post.company, post.text).subscribe({
      next: (res) => {
        this.generatedDrafts[post.id] = res.draft;
        this.isGeneratingDraft[post.id] = false;
      },
      error: (err) => {
        console.error(err);
        this.isGeneratingDraft[post.id] = false;
      }
    });
  }

  exportData(format: 'csv' | 'excel') {
    const data = this.filteredDownloadPosts;
    if (data.length === 0) return;

    let csvContent = 'Company,Date,Post Description,Content Classification,Engagement Score\n';
    
    data.forEach(p => {
      const company = `"${p.company.replace(/"/g, '""')}"`;
      const date = `"${new Date(p.timestamp).toISOString().split('T')[0]}"`;
      const desc = `"${p.text.replace(/"/g, '""')}"`;
      const classification = `"${p.analysis?.content_classification || ''}"`;
      const engagement = p.engagement_score;
      csvContent += `${company},${date},${desc},${classification},${engagement}\n`;
    });

    const blob = new Blob([csvContent], { type: format === 'csv' ? 'text/csv;charset=utf-8;' : 'application/vnd.ms-excel;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `linkedin_analytics_${format}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  downloadCSV() {
    this.exportData('csv');
  }

  downloadExcel() {
    this.exportData('excel');
  }

  getParsedDraft(draft: string): string {
    return marked.parse(draft) as string;
  }

  // Icons
  iconBuilding = "M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V5h2v2zm10 12h-8V9h8v10zm-2-8h-4v2h4v-2zm0 4h-4v2h4v-2z";
  iconClock = "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67V7z";
  iconBell = "M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6V11c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C9.63 5.36 8 7.92 8 11v5l-2 2v1h16v-1l-2-2z";
  iconWarning = "M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z";
  iconCheck = "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z";
  iconTrend = "M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6h-6z";
  iconChart = "M5 9.2h3V19H5zM10.6 5h2.8v14h-2.8zm5.6 8H19v6h-2.8z";
  iconDownload = "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z";
  iconSearch = "M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z";
  iconThumb = "M1 21h4V9H1v12zm22-11c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.59 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2z";
  iconChat = "M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z";
  iconRepeat = "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z";
  iconBolt = "M7 2v11h3v9l7-12h-4l4-8z";
  iconChecklist = "M3 5h2v2H3zm0 4h2v2H3zm0 4h2v2H3zm4-8h14v2H7zm0 4h14v2H7zm0 4h14v2H7z";
}
