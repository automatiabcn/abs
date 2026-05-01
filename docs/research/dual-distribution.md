# ABS Çift Dağıtım Stratejisi

Bu belge, ABS ürününün pazara sunulması ve dağıtımına yönelik aşamalı stratejiyi detaylandırmaktadır. Temel yaklaşımımız, başlangıçta kendi sunucusunda barındırma (self-host) seçeneğine odaklanarak erken gelir elde etmek ve ardından yönetilen bulut (managed cloud) hizmetini aşamalı olarak sunmaktır.

## ABS Çift Dağıtım Stratejisi Özeti (Aşamalı)

ABS'nin dağıtım stratejisi, pazarın farklı segmentlerine hitap etmek ve ürünün gelişimini sürdürülebilir bir şekilde finanse etmek amacıyla aşamalı bir yaklaşıma dayanmaktadır. İlk aşamada, teknik yeterliliğe sahip ve verileri üzerinde tam kontrol isteyen müşterilere yönelik self-host çözümü önceliklendirilecektir. İkinci aşamada, operasyonel yükü üstlenmek istemeyen veya hızlı başlangıç arayan müşteriler için yönetilen bulut hizmeti beta olarak sunulacak, ardından tam lansman yapılacaktır.

## Faz 1: Self-host (Ay 1-3) — Öncelik ve Gelir Kaynağı

**Süre:** 1. aydan 3. aya kadar.

Bu ilk aşamada, ABS'nin self-host sürümünün satışına öncelik verilecektir. Müşterilere ömür boyu lisans için 299 dolar fiyatla sunulacaktır. Bu yaklaşımın temel hedefleri şunlardır:
- Erken aşamada önemli bir gelir akışı sağlamak.
- Ürünün temel değer önerisini teknik kullanıcılara ulaştırmak.
- Bulut altyapısı geliştirme ve operasyonel yükü minimumda tutarak ürün geliştirmeye odaklanmak.
- Müşteri geri bildirimlerini self-host ortamında toplayarak ürün olgunluğunu artırmak.

## Faz 2: Managed Cloud Beta (Ay 3-6) — Küçük Grup

**Süre:** 3. aydan 6. aya kadar.

Faz 1'deki satış ve geri bildirimlerden sonra, yönetilen bulut hizmetinin beta sürümü sınırlı sayıda müşteriye sunulacaktır.
- **Fiyatlandırma:** Aylık 79 dolar.
- **Müşteri Sayısı:** 3-5 müşteri ile sınırlı olacaktır.
- **Amaç:** Bulut altyapısının stabilitesini, performansını ve operasyonel süreçlerini test etmek. Müşteri deneyimini değerlendirmek ve geri bildirimler doğrultusunda hizmeti iyileştirmek. Bu aşama, solo bir kurucunun yönetilebilir müşteri sayısını (yaklaşık 20-30 müşteri) aşmadan bulut operasyonlarını öğrenmesi için kritik öneme sahiptir.

## Faz 3: Managed Cloud Tam Açılış (Ay 6+)

**Süre:** 6. aydan itibaren.

Beta aşamasından elde edilen öğrenimler ve iyileştirmeler tamamlandıktan sonra, yönetilen bulut hizmeti tüm müşterilere açılacaktır. Bu aşamada, fiyatlandırma ve özellik setleri Faz 2'deki beta sürümünden farklılaşabilir ve daha geniş bir kitleye hitap edecek şekilde optimize edilebilir.

## Karşılaştırma Tablosu: Self-Host vs Managed Cloud (Müşteri İçin Artı/Eksi)

| Özellik | Self-Host | Managed Cloud |
|---|---|---|
| **Artıları** | Tam veri kontrolü ve gizliliği | Kurulum ve bakım gerektirmez |
|  | Tek seferlik ödeme ($299 ömür boyu lisans) | Yüksek erişilebilirlik (SLA) |
|  | Özelleştirme ve entegrasyon esnekliği | Otomatik yedeklemeler + güvenlik |
|  | Altyapı maliyetlerinde potansiyel tasarruf | 7/24 izleme ve destek |
| **Eksileri** | Kurulum, yapılandırma ve bakım sorumluluğu | Veri kontrolünün bir kısmı sağlayıcıda |
|  | Teknik bilgi ve beceri gerektirir | Tekrarlayan aylık maliyetler |
|  | Güvenlik güncellemeleri ve yedeklemelerin yönetimi | Özelleştirmede sınırlamalar |
|  | Çalışma süresi (uptime) garantisi olmaması | Sağlayıcıya bağımlılık riski |

## Solo Operatör İçin Yük Analizi

Tek bir kurucu olarak yönetilen bulut hizmeti sunmak, önemli operasyonel yükler getirmektedir:
- **Uptime SLA:** Müşterilere belirli bir çalışma süresi garantisi vermek, sürekli izleme ve hızlı müdahale gerektirir.
- **Yedeklemeler:** Düzenli ve güvenilir yedekleme stratejileri oluşturmak, test etmek ve sürdürmek kritik.
- **7/24 İzleme:** Sistemlerin kesintisiz izlenmesi, solo bir kurucu için zorlayıcı.
- **Müşteri Desteği:** Müşteri sorularına hızlı ve etkili yanıt vermek zaman ve kaynak gerektirir.

Solo bir kurucunun yönetilebilir müşteri sayısı yaklaşık **20-30** ile sınırlıdır. Bu eşik aşılması, hizmet kalitesi düşüşüne veya kurucu tükenmişliğine yol açabilir. Faz 2'de beta müşteri sayısı bu nedenle düşük tutulmuştur.

## Rakip Çift Dağıtım Kıyaslamaları

| Ürün | Self-Host | Managed Cloud |
|---|---|---|
| Plausible | Ücretsiz (AGPLv3) | $9/ay |
| Umami | Ücretsiz | $20/ay |
| Supabase | Mevcut | Free tier + $25/ay (Pro) |
| Ghost | $4/ay (altyapı) | $18/ay |
| n8n | Ücretsiz (Community) | €20/ay (Cloud Starter) |
| Cal.com | Ücretsiz | $15/kullanıcı/ay (Team) |

Çoğu rakip self-host'u ücretsiz/düşük maliyetli sunarken, managed cloud için subscription ücret alıyor. ABS modelinde self-host **ücretli** ($299 one-time) — bu fark kasıtlı, solo operatör için sürdürülebilir gelir sağlar.

## Customer Migration — Self-host'tan Cloud'a Taşıma (Gelecekte)

Gelecekte, self-host kullanan müşterilerin yönetilen bulut hizmetine geçiş yapabilmeleri için bir yol sunulacaktır. Bu geçiş, mevcut verilerin dışa aktarılması (export) ve bulut ortamına içe aktarılması (import) mekanizmaları aracılığıyla sağlanacaktır. ABS Profile Export (`.abs` format, daha önceki SERVER geliştirmelerinde implement edildi) bu migration için temel olabilir.

## Altyapı Kararı: VPS Başlangıç, Kubernetes Sonra

Faz 2 başlangıçta, yönetilen bulut hizmeti için altyapı tercihi **Sanal Özel Sunucular (VPS)** yönünde olacaktır. Hetzner gibi sağlayıcılardan aylık 100-300 dolar maliyetle sunulan özel sunucular, Kubernetes'e kıyasla kurulum ve yönetim açısından daha basittir. Bu, solo kurucunun operasyonel yükünü azaltarak ürün geliştirmeye odaklanmasını sağlar.

Çok kiracılı (multi-tenant) bulut ortamı için veri izolasyonu kritik. Başlangıçta şema-bazlı ayırma, müşteri sayısı arttıkça PostgreSQL Row-Level Security (RLS) veya ayrı veritabanlarına geçiş yapılacaktır.

---

Faz 2 başlarken `docs/operations.md`'ye detaylı cloud hosting playbook eklenecek.
