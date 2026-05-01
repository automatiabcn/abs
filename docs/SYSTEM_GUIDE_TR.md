# ABS Sistem Rehberi — Teknoloji + Özellikler + Kullanım



## 1. Teknoloji Stack

| Teknoloji | Katman | Ne için |
| :--- | :--- | :--- |
| **Anthropic Claude (Sonnet/Opus)** | LLM | Karmaşık reasoning, analiz ve kalite kontrolü gerektiren görevler için. Toplam trafiğin %5-15'ini oluşturur. |
| **Groq** | LLM | Llama 3.3-70B, GPT-OSS-120B, Qwen3-32B, Kimi-K2, Llama-4-Scout, Llama-3.1-8B modellerini çalıştıran, ücretsiz ve ultra hızlı birincil cascade katmanı. |
| **Cerebras** | LLM | Wafer-scale mimarisi ile ultra-hızlı Llama 3.3 70B inference. |
| **Gemini** | LLM | Flash, Pro, search, URL, resim ve video işleme yetenekleri; 1M token context. |
| **Cohere** | LLM | Aya 8B (Türkçe), Command R+ ve Rerank v3 ile çok dilli ve RAG doğruluk artırımı. |
| **Cloudflare Workers AI** | LLM | Kimi K2.5 modeli için hobi katmanı ($0) ve edge inference. |
| **Ollama (yerel)** | LLM | Müşterinin kendi PC GPU'sunda yerel çalıştırma: Llama 3.3 70B, Qwen 2.5, DeepSeek-V3, qwen2.5-coder, codellama, phi4, gemma2, llava. |
| **MLX (Apple M4)** | LLM | Apple M-serisi çiplerin Neural Engine'i üzerinde 0.3-1s gecikme ile Llama3 ve Phi3 çalıştırma. |
| **OpenRouter** | LLM | 200+ model içeren marketplace; ana provider'lar çöktüğünde fallback olarak kullanılır. |
| **vLLM** | LLM | Müşterinin kendi GPU altyapısında self-host inference için. |
| **Qdrant** | Vector DB | Multi-tenant payload filtreleme ile kiracı verisi izolasyonu. 8M vektörde p95<150ms sorgu hızı. |
| **BGE-M3** | Embedding | 1024-dim, çok dilli (TR+EN+ES+100 dil) metin embedding modeli. |
| **Qwen3-Reranker-4B** | Reranker | Cross-encoder ile RAG'den dönen top-3 sonucu yeniden sıralayarak doğruluğu +%30 artırır. |
| **WhisperX** | Transcription | Toplantı ses kayıtlarını deşifre eder ve `pyannote` ile konuşmacıları ayırır (diarization). |
| **Piper TTS** | TTS | MIT lisanslı, tr_TR/en_US/es_ES dillerinde metinden sese dönüştürme (CPML lisanslı alternatifler reddedildi). |
| **meetily** | Meeting bot | `Recall.ai` alternatifi, yerel olarak toplantı kaydı alır. |
| **NATS + JetStream** | Event bus | Mikroservisler arası asenkron ve dayanıklı (durable) iletişim. |
| **Inngest** | Workflow engine | Backend'de state'i koruyan, dayanıklı (durable) iş akışları yönetimi. |
| **n8n** | Workflow UI | Müşteriye yönelik, görsel iş akışı (workflow) editörü. |
| **Cerbos** | Authorization | `tenant_id` bazlı ön filtreleme ile yetkilendirme. Yetkisiz isteği (403) uygulama katmanına ulaşmadan engeller. |
| **Microsoft Presidio** | PII redaction | T.C. kimlik no, telefon, kredi kartı gibi kişisel ve hassas verileri otomatik olarak maskeler. |
| **HMAC chain** | Audit log | Her audit log kaydını bir önceki kaydın hash'i ile zincirleyerek kurcalanmasını (tampering) engeller. |
| **LangFuse** | Observability | LLM çağrılarının trace, maliyet ve gecikme metriklerini izler. ClickHouse OLAP üzerinde çalışır. |
| **RAGAS** | Quality eval | RAG cevaplarının kalitesini ölçer: Faithfulness, Answer Relevance, Precision/Recall. |
| **Vanna AI** | Text2SQL | Doğal dilde yazılan sorguları SQL'e çevirerek veritabanından veri çeker. |
| **Microsoft Graph** | Gmail MCP | OAuth 2.0 PKCE ile güvenli, self-host Gmail entegrasyonu. |
| **Next.js 15 SSR** | Frontend | Müşteri portalı ve yönetim paneli. |
| **Helm** | Deployment | Kubernetes üzerinde tüm sistemi bir umbrella chart ile yönetir. |
| **Alembic** | DB migration | SQLModel ile entegre, PostgreSQL şema değişikliklerini yönetir. |
| **GitHub Actions** | CI/CD | Kod test ve deploy pipeline'ları. |
| **Docker Compose** | Dev environment | Yerel (local) ve hazırlık (staging) ortamlarını kurar. |
| **FastAPI** | Backend framework | Python 3.11 tabanlı ana API sunucusu. |
| **SQLModel** | ORM | Type-safe veritabanı erişimi. |
| **PostgreSQL** | Primary DB | Kiracı (tenant) verilerinin tutulduğu ana veritabanı. |
| **ClickHouse** | Analytics DB | LangFuse trace verilerinin depolandığı analitik veritabanı. |
| **Redis** | Cache + queue | Oturum (session) yönetimi ve 5 dakikalık anlamsal önbellek (semantic cache). |

---

## 2. Özellikler

### 2.1 ABS Orchestra (Cascade Router)
- **NE:** 6'dan fazla LLM provider'ını (Groq, Gemini, Anthropic vb.) maliyet, hız ve görev karmaşıklığına göre akıllıca yönlendiren bir router katmanıdır.
- **NE İÇİN:** LLM maliyetlerini minimize etmek için. Basit görevleri ücretsiz veya çok ucuz provider'lar üzerinden çözerek toplam harcamanın %85-95'ini ücretsiz yollara kaydırır. Sadece karmaşık görevler için ücretli provider'ları (örn. Anthropic Opus) devreye sokar.
- **NASIL KULLANILIR:** Kurulum sihirbazında (Setup Wizard) sahip olduğunuz provider API anahtarlarını girmeniz yeterlidir. Sistem, en uygun maliyetli zinciri (chain) otomatik olarak oluşturur. API çağrısı yaparken `skip_paid_providers: true` parametresini göndererek Anthropic gibi ücretli provider'ları tamamen atlayabilirsiniz.

### 2.2 Quality Pipelines (qual_*)
- **NE:** `qual_code`, `qual_tr`, `qual_analysis`, `qual_translate`, `qual_human`, `qual_code_human` gibi önceden tanımlanmış, çok adımlı kalite artırma zincirleridir. Bir "üret-doğrula-düzelt" (generate-verify-refine) mantığıyla çalışırlar.
- **NE İÇİN:** Tek bir LLM çağrısından daha yüksek kalitede ve doğruluğu kontrol edilmiş sonuçlar elde etmek için. Örneğin, `qual_code` pipeline'ı önce kodu üretir, sonra başka bir modelle test senaryoları yazar, sonra da hataları ayıklar.
- **NASIL KULLANILIR:** API çağrısı yaparken `pipeline` parametresini istediğiniz pipeline adıyla belirtin. Örnek: `pipeline=qual_code`.

### 2.3 Race Patterns
- **NE:** `race`, `race_code`, `race_tr`, `race_local` gibi, N sayıda LLM modelini aynı görev için paralel olarak çalıştıran ve ilk başarılı cevabı döndüren bir şablondur.
- **NE İÇİN:** Hızın en kritik öncelik olduğu senaryolar için. Bir provider yavaşladığında veya hata verdiğinde, diğerleri görevi tamamlar ve kullanıcı beklemez.
- **NASIL KULLANILIR:** API çağrısı yaparken `pattern=race` parametresini kullanın. Sistem, o görev için uygun olan modelleri (örn. `race_code` için kodlama modelleri) paralel olarak çalıştırır.

### 2.4 RAG Sistemi (Multi-Tenant)
- **NE:** Qdrant, BGE-M3, Qwen3-Reranker ve Anthropic Contextual Chunking teknolojilerini birleştiren, RAGAS ile kalite denetimi yapılan, çok-kiracılı (multi-tenant) bir "Retrieval-Augmented Generation" sistemidir.
- **NE İÇİN:** Şirketinizin dahili dokümanlarını, geçmiş projelerini, toplantı notlarını ve diğer metin tabanlı verilerini sorgulanabilir bir kurumsal hafızaya dönüştürmek için.
- **NASIL KULLANILIR:** Doküman yüklemek için `/v1/rag/ingest` endpoint'ine POST isteği yapın. Sorgu yapmak için `/v1/rag/query` endpoint'ini kullanın. Kiracı (tenant) veri izolasyonu, Qdrant'ın payload filtreleri sayesinde otomatik olarak sağlanır; bir kiracı diğerinin verisini göremez.

### 2.5 Provider Degradation Matrix
- **NE:** Müşterinin 0'dan 6'ya kadar eksik API anahtarı girmesi senaryolarını yöneten bir "graceful degradation" mekanizmasıdır.
- **NE İÇİN:** Müşteriyi tüm provider'lara (Groq, Gemini, Anthropic vb.) üye olup API anahtarı almak zorunda bırakmamak için. Sistem, mevcut olan anahtarlarla çalışmaya devam eder, eksik olanları cascade path'lerinden çıkarır.
- **NASIL KULLANILIR:** Kurulum sırasında sadece sahip olduğunuz API anahtarlarını girin. Girmedikleriniz, panelde gri ve "disabled" olarak görünür. Sistem, bu provider'ları atlayarak çalışacak şekilde kendini otomatik olarak yapılandırır.

### 2.6 Magic-Link Multi-Admin
- **NE:** E-posta tabanlı, parolasız bir self-signup ve login sistemidir. Kullanıcı kaydolur, 24 saat geçerli bir token içeren bir e-posta alır, linke tıklayarak hesabını "claim" eder ve kalıcı (DB-first) bir login oturumu başlatır.
- **NE İÇİN:** Bir tenant altında birden fazla yöneticinin (admin) birbirinden bağımsız ve güvenli bir şekilde çalışabilmesi için.
- **NASIL KULLANILIR:** Yeni bir admin eklemek için `/signup` adresine yönlendirin. E-postasını girdikten sonra gelen kutusundaki "magic-link"e tıklar ve doğrudan `/panel`'e erişir.

### 2.7 Plugin Marketplace
- **NE:** Slack receiver, Gmail archiver, Linear bridge, Notion sync, Postgres mirror gibi hazır entegrasyonların bulunduğu bir marketplacedir. Her plugin `cosign` ile imzalanmış ve izole bir sandbox profilinde çalışır.
- **NE İÇİN:** Harici sistemlerle entegrasyonu kod yazmadan, tek tıkla sağlamak için.
- **NASIL KULLANILIR:** `/admin/marketplace` adresine gidin, istediğiniz plugin'i seçin ve "Tenant'a Yükle" butonuna tıklayın. Gerekli yetkileri onayladıktan sonra plugin aktif hale gelir.

### 2.8 NL Workflow Builder
- **NE:** Doğal dilde yazılmış bir komutu (örn. "Yeni bir müşteri e-postası geldiğinde, içeriğini analiz et ve bir Linear issue oluştur") Inngest tarafından çalıştırılabilir bir JSON iş akışına (workflow) dönüştüren bir araçtır.
- **NE İÇİN:** Teknik olmayan kullanıcıların bile kod yazmadan karmaşık otomasyonlar kurabilmesi için.
- **NASIL KULLANILIR:** `/admin/workflow-builder` adresine gidin. Metin kutusuna otomasyon tarifinizi yazın ve "Synthesize" butonuna tıklayın. Sistem bir iş akışı grafiği oluşturur. "Dry run" ile test edip "Save" ile kaydedebilir ve "Execute" ile çalıştırabilirsiniz.

### 2.9 Meetings & Transcription
- **NE:** Ses dosyası (audio) yüklemelerini kabul eden, WhisperX ile deşifre edip konuşmacıları ayıran, LLM ile özet ve aksiyon maddeleri çıkaran ve Piper TTS ile sesli özet üreten bir pipeline'dır.
- **NE İÇİN:** Toplantı kayıtlarını metne dökme, önemli kararları ve görevleri otomatik olarak çıkarma ve arşivleme sürecini otomatikleştirmek için.
- **NASIL KULLANILIR:** `/panel/meetings` sayfasına gidin ve ses dosyasını yükleyin. Deşifre metni (transcript), özet ve aksiyon maddeleri birkaç dakika içinde otomatik olarak ekranda belirir.

### 2.10 Quota Tracker
- **NE:** Ücretli (Claude Plus) ve 5 ücretsiz provider için aylık kullanımınızı takip eden bir izleme sistemidir.
- **NE İÇİN:** Aylık $20'lık bütçe limitinin aşılmasını engellemek için. Kullanım %80 ve %95 eşiklerine ulaştığında uyarılar gönderir.
- **NASIL KULLANILIR:** `/panel/quota` sayfasından gerçek zamanlı kullanımınızı bir bar grafiği üzerinde takip edebilirsiniz.

### 2.11 Quality Gates (Opus Baseline)
- **NE:** Her RAG cevabının RAGAS `faithfulness` skorunun 0.85'in üzerinde olmasını ve haftalık olarak ABS cascade sisteminin Opus'a karşı kazanma oranının (win rate) en az %50 olmasını zorunlu kılan otomatik kalite kontrol mekanizmalarıdır.
- **NE İÇİN:** Halüsinasyon oranını <%3 seviyesinde tutmayı garanti etmek ve sistemin genel kalitesinin endüstri standardının (Opus) altında kalmamasını sağlamak için.
- **NASIL KULLANILIR:** Bu özellik tamamen otomatiktir. Her cevap üretildiğinde arka planda bu kontroller çalışır. Kalite eşiğinin altına düşen cevaplar kullanıcıya gösterilmeden önce yeniden üretilir veya işaretlenir.

### 2.12 13 Mimari Katman (Self-Host Production)
- **NATS+Inngest event bus:** Asenkron servis iletişimi.
- **Cerbos auth pre-filter:** Yetkilendirme kontrolü.
- **MCP Gateway 122+ tool:** Harici araç entegrasyonları.
- **RAG (Bölüm 2.4):** Kurumsal hafıza.
- **Vanna AI text2SQL:** Doğal dil ile veritabanı sorgulama.
- **Meeting Pipeline (WhisperX+Piper TTS+meetily):** Toplantı otomasyonu.
- **Inngest Workflow + n8n customer-facing:** İş akışı motoru ve arayüzü.
- **LangFuse observability:** LLM operasyonları izleme.
- **Quality Pipelines (Bölüm 2.2):** Kalite artırma zincirleri.
- **Next.js 15 portal:** Müşteri paneli.
- **News Watcher 7-source:** 7 kaynaktan haber takibi.
- **Gmail MCP (Microsoft Graph self-host OAuth 2.0 PKCE):** Güvenli e-posta entegrasyonu.
- **CI/CD GitHub Actions + Helm + Alembic:** Otomatik deploy ve veritabanı yönetimi.

---

## 3. Kurulum (Step-by-Step)

### 3.1 Sistem Gereksinimleri
- **Sunucu:** 4-8 vCPU, 16-32GB RAM. Opsiyonel GPU: NVIDIA T4 / RTX 4090 (yerel LLM'ler için).
- **Disk:** Minimum 50GB (Docker imajları, modeller ve veritabanları için).
- **Yazılım:** Docker ve Docker Compose (veya Kubernetes/Helm).
- **Ağ:** Statik IP adresi veya bir domain adı (opsiyonel, SSL için önerilir).

### 3.2 Adım 1: Repo Clone
Sistemin kurulum dosyalarını içeren Git reposunu klonlayın.
```bash
git clone https://github.com/automatiabcn/abs-server-product.git
cd abs-server-product
```

### 3.3 Adım 2: Helm Chart Deploy (Production)
Kubernetes üzerinde production ortamı için Helm chart'ını kullanın.
```bash
# values-prod.yaml dosyasını kendi konfigürasyonunuza göre düzenleyin
helm install abs ./infra/helm/abs --values values-prod.yaml
```
Geliştirme (development) veya test ortamı için Docker Compose kullanabilirsiniz.
```bash
# Geliştirme ortamı için
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d
```

### 3.4 Adım 3: Setup Wizard (6 adım)
Kurulum tamamlandıktan sonra tarayıcınızdan sunucu IP adresine veya domain'ine gidin. `/setup` adresine yönlendirileceksiniz.
- **Step 1:** İlk yönetici (admin) için bir e-posta adresi ve parola belirleyin.
- **Step 2:** Lisans anahtarınızı girin (14 günlük demo lisansı otomatik olarak sağlanır).
- **Step 3:** Sistemin çalışacağı domain adını veya IP adresini belirtin (Internal CA desteği mevcuttur).
- **Step 4:** Anthropic API anahtarınızı girin (Opsiyonel, `skip_paid_providers` ile atlanabilir).
- **Step 5:** Diğer provider API anahtarlarını girin: Groq, Gemini, Cerebras, Cohere, Cloudflare (Tümü opsiyoneldir).
- **Step 6:** "Test Ping" butonu ile girilen anahtarların ve servislerin çalışıp çalışmadığını kontrol edin.

### 3.5 Adım 4: İlk Login + Panel
Kurulum sihirbazı tamamlandıktan sonra `/panel/login` adresine gidin ve Adım 1'de oluşturduğunuz yönetici bilgileriyle giriş yapın. `/panel` ana sayfası, sistem widget'larını ve MCP (Mission Control Panel) envanterini gösterir.

### 3.6 Adım 5: Plugin Marketplace
- `/admin/marketplace` adresine gidin.
- Listelenen 5 temel plugin'i (Slack, Gmail, Linear, Notion, Postgres) bulun.
- Her biri için "Tenant'a Yükle" butonuna tıklayarak entegrasyonları aktif hale getirin.

### 3.7 Adım 6: İlk Workflow
- `/admin/workflow-builder` adresine gidin.
- Prompt kutusuna şu metni yazın: `"Bir Slack mesajı geldiğinde, içeriğinden bir Linear issue oluştur ve özetini sesli olarak bana DM gönder."`
- **Synthesize**'e tıklayın.
- **Dry run** ile adımları kontrol edin.
- **Save** ile kaydedin ve **Execute** ile çalıştırın.

### 3.8 Adım 7: Quota + Audit Kontrol
- `/panel/quota` adresinden anlık LLM kullanımınızı izleyin.
- API üzerinden `/v1/admin/audit/recent` endpoint'ini sorgulayarak son sistem olaylarının denetim (audit) kaydını kontrol edin.

---

## 4. Kullanım — Workflow Tasarımı (Detaylı)

### 4.1 Müşteri Toplantı Otomasyonu Senaryosu
Bu senaryo, saatler süren manuel toplantı deşifre ve özetleme işini saniyelere indirir.

1.  **Trigger:** Kullanıcı, `/panel/meetings` arayüzünden bir toplantı ses kaydını (.wav, .mp3, .m4a) yükler.
2.  **WhisperX transcribe:** Sistem, dosyayı alır ve WhisperX ile metne dönüştürür. `pyannote` kütüphanesi ile konuşmacıları (Speaker 01, Speaker 02) ayırır. (10 dakikalık bir ses kaydı için ~16 saniye).
3.  **Cascade LLM:** Deşifre metni, aksiyon maddelerini (action items) çıkarmak için ABS Orchestra'ya gönderilir. Groq üzerindeki Llama 3.3 birincil model olarak kullanılır; başarısız olursa fallback zinciri devreye girer.
4.  **Linear ticket create:** Çıkarılan her aksiyon maddesi için Linear API kullanılarak bir görev (ticket) oluşturulur. Sistem, yeni görev başlığı ile mevcut görevler arasında kosinüs benzerliği (cosine similarity) kontrolü yaparak duplike görev oluşturmayı engeller.
5.  **Piper TTS özet:** Toplantının bir paragraflık özeti Piper TTS motoru ile ses dosyasına dönüştürülür ve ilgili kişiye Slack üzerinden DM olarak gönderilir.
6.  **Qdrant embed:** Toplantının deşifresi ve özeti, BGE-M3 ile vektörlere dönüştürülür ve ilerideki RAG sorguları için Qdrant veritabanına kaydedilir.
7.  **LangFuse trace:** Bu 6 adımın her birinin gecikme, maliyet ve sonuçları LangFuse'a loglanır.

**Toplam Süre:** Manuel olarak saatler sürecek bu işlem, otomasyon ile yaklaşık **30 saniyede** tamamlanır.

### 4.2 Custom Workflow Oluşturma
- **Adım 1:** `/admin/workflow-builder` adresine gidin.
- **Adım 2:** Doğal dil (NL) prompt kutusuna amacınızı yazın. Örnek: `"Gmail destek kutusuna gelen her e-postayı oku. İçeriği 'urgent' kelimesini içeriyorsa bana Slack'ten DM at. İçermiyorsa, 'Destek Talepleri' projesinde bir Linear ticket oluştur."`
- **Adım 3:** "Synthesize" butonuna tıklayın. Sistem, bu prompt'u analiz eder ve 4-6 adımdan oluşan bir iş akışı grafiği (graph) oluşturur.
- **Adım 4:** "Dry run" butonuna tıklayarak iş akışının adımlarını (step plan) ve tahmini çalışma süresini (`estimate_s`) kontrol edin.
- **Adım 5:** "Save" ile iş akışını veritabanına kaydedin.
- **Adım 6:** "Execute" ile iş akışını Inngest kuyruğuna gönderin. Sistem, ilgili trigger'ı (örn. yeni Gmail) dinlemeye başlar.

### 4.3 RAG Bilgi Tabanı Kurma
- **Adım 1 (Ingest):** `POST /v1/rag/ingest` endpoint'ine `multipart/form-data` olarak dokümanlarınızı (PDF, MD, TXT) yükleyin.
- **Arka Plan:** Sistem, dokümanları Anthropic'in Contextual Chunking yöntemiyle anlamlı parçalara ayırır, BGE-M3 ile vektörlere dönüştürür ve Qdrant'a kaydeder.
- **Adım 2 (Query):** `POST /v1/rag/query` endpoint'ine JSON body içinde sorunuzu gönderin.
- **Arka Plan:** Sistem, sorunuzu embed eder, Qdrant'tan en ilgili top-3 parçayı (chunk) çeker, Qwen3-Reranker ile yeniden sıralar ve bu context'i bir LLM'e göndererek kaynakçalı (citation) bir cevap üretir.

### 4.4 Plugin Aktivasyon
- **Adım 1:** `/admin/marketplace`'ten bir plugin seçin (örn. Notion Sync).
- **Adım 2:** "Tenant'a Yükle" butonuna tıklayın.
- **Arka Plan:** Sistem, plugin'in `cosign` imzasını doğrular. Cerbos ile plugin'in talep ettiği izinlerin tenant politikalarınıza uygun olup olmadığını kontrol eder.
- **Adım 3:** Onayınızla, plugin izole bir sandbox ortamında (256MB RAM, 0.5 CPU limiti) başlatılır ve aktif hale gelir.

### 4.5 Multi-Admin Davet
- **Adım 1:** Yeni eklemek istediğiniz admin'e sisteminizin `/signup` linkini gönderin.
- **Adım 2:** Yeni admin, e-posta adresini girer. Sistem, 24 saat geçerli bir magic-link içeren bir e-posta gönderir.
- **Adım 3:** Yeni admin, e-postadaki linke tıklar (`/auth/magic?token=...`).
- **Arka Plan:** Sistem, token'ı doğrular, hesabı "claim" eder ve kalıcı bir veritabanı oturumu oluşturur. Bu, token'ın tekrar kullanılamayacağı anlamına gelir (claim rotate).
- **Adım 4:** Yeni admin, doğrudan `/panel`'e yönlendirilir. Artık kendi e-posta ve parolasıyla (veya yeni magic-link isteyerek) giriş yapabilir.

---

## 5. Pilot/PoC Seçenekleri

| Seçenek | Fiyat | İçerik | İade |
| :--- | :--- | :--- | :--- |
| **PoC (Proof of Concept)** | $299 lifetime | Helm chart + dokümantasyon + temel e-posta desteği. | 14 gün koşulsuz iade. |
| **Pilot** | Custom quote | 2 hafta boyunca sizin sistemlerinizle özel entegrasyon ve yerinde destek. | Müzakere edilir. |
| **Beta** | $0 (30 gün) | Tam sürüm erişimi, feedback ortağı olma karşılığında. | — |

İletişim ve sorularınız için: **support@automatiabcn.com**

---

**Doküman versiyonu:** 4.0 — 2026-04-30 — Teknik referans 
**Yazar:** Enes (Automatiabcn kurucusu)
