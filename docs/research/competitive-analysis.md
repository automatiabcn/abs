# Rekabet Analizi: ABS

Bu belge, ABS'nin rekabet ortamındaki konumunu, temel rakiplerini, ayırt edici özelliklerini ve hedef pazarını detaylandırmaktadır.

## 1. Rekabet Haritası

ABS, geliştiricilerin ve ekiplerin yapay zeka destekli kodlama deneyimini optimize etmeye odaklanmış bir araçtır. Doğrudan bir rakibi olmamakla birlikte, pazar çeşitli çözümlerle doludur. Bu çözümler, proxy hizmetlerinden tam teşekküllü ajan platformlarına, IDE entegrasyonlarından kurumsal seviye kod asistanlarına kadar geniş bir yelpazeyi kapsar. ABS, bu geniş yelpazede, özellikle Claude Code kullanıcılarını hedefleyerek, maliyet etkinliği, özelleştirme ve kalite odaklı benzersiz bir değer sunar.

## 2. Rakip Kategorileri

### Proxy ve Ağ Geçidi Hizmetleri
LLM API'lerine erişimi kolaylaştıran veya maliyet/performans optimizasyonu sunan hizmetler.
- **LiteLLM**: Açık kaynaklı sağlayıcı proxy'si. Kanca (hook), RAG, yargıç veya panel gibi gelişmiş özellikler sunmaz.
- **Vercel AI Gateway**: Token başına ödeme (PAYG) modeliyle API ağ geçidi. İşaretleme yok.
- **OpenRouter**: Birleşik API erişimi sunar, %5.5 platform ücreti alır.
- **AWS Bedrock**: Token başına ödeme modeli.
- **Azure OpenAI Service**: Token başına ödeme ve ayrılmış kapasite (PTU) seçenekleri.

### Ajan ve Düşük Kodlu Platformlar
- **Dify**: Ajan platformu, Pro planı $59/ay. Düşük kodlu yaklaşım.
- **FlowiseAI**: Bulut sürümü $35/ay.
- **n8n AI**: İş akışı otomasyonu, €20/ay.

### IDE Entegre ve Terminal Araçları
- **Cursor CLI**: IDE'ye bağlı.
- **Claude Code vanilla**: Anthropic'in temel aracı, ABS bunu genişletir.
- **Aider**: Terminal aracı, MCP sunucu uyumlu. ABS, Aider'ı bir araç olarak kullanır.
- **Cline/Roo Code**: VS Code uzantısı, LLM maliyetiyle birlikte $100-120/geliştirici/ay.
- **Continue.dev**: Token başına ödeme ($3/M token) ve ekip için $20/kullanıcı/ay.

### Kurumsal Kod Asistanları
- **Sourcegraph Cody Enterprise**: $59/kullanıcı/ay. Sembol farkındalıklı RAG sunar.
- **Tabnine Enterprise**: $39/kullanıcı/ay.
- **Codeium/Windsurf**: Pro $15/ay, Ekipler için $24/kullanıcı/ay.
- **GitHub Copilot Enterprise**: $60/kullanıcı/ay (39 + 21).
- **Amazon Q Developer Enterprise**: Özel fiyatlandırma.
- **Gemini Code Assist Enterprise**: $45/kullanıcı/ay.

### Gözlemlenebilirlik ve Yönetim
- **Helicone**: $20/kullanıcı/ay gözlemlenebilirlik.
- **LangSmith**: $39/kullanıcı/ay.

## 3. Karşılaştırma Tablosu (Öne Çıkan Özellikler)

| Özellik / Rakip | ABS | LiteLLM | Dify | Cline/Roo | Continue.dev | Sourcegraph Cody | GitHub Copilot | Vercel Gateway |
|---|---|---|---|---|---|---|---|---|
| **Self-Host** | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| **Tek Seferlik Fiyat** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Hook Sistemi** | ✅ | ❌ | ✅ | Kısmen | Kısmen | Kısmen | ❌ | ❌ |
| **RAG** | ✅ | ❌ | ✅ | Kısmen | ✅ | ✅ | Kısmen | ❌ |
| **Kalite Pipeline** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Türkçe Destek** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Çoklu Sağlayıcı** | ✅ | ✅ | ✅ | Kısmen | ✅ | ✅ | ❌ | ✅ |

## 4. ABS'nin 8 Ayırt Edici Özelliği

1. **Türkçe Kalite Pipeline'ları (qual-tr)**: ABS, özellikle Türkçe dilinde yüksek kaliteli kod üretimi ve analizi için optimize edilmiş benzersiz pipeline'lar sunar. Türkiye pazarında veya Türkçe içerikle çalışan ekipler için kritik bir avantaj.

2. **Claude Code Uzantı Stratejisi**: ABS, Claude Code'un yerini almak yerine, onun yeteneklerini genişleten ve mevcut deneyimi bozmadan zenginleştiren bir uzantı olarak konumlanır. Kullanıcıların alışkanlıklarını değiştirmeden daha fazla değer elde etmelerini sağlar.

3. **75 Önceden Oluşturulmuş MCP Aracı**: ABS, geliştirme süreçlerini hızlandıran 75'ten fazla önceden yapılandırılmış MCP aracı ile gelir. Anında kullanıma hazır.

4. **Ücretsiz Katmanlı Maliyet Optimizasyonu**: ABS, kademeli bir ücretsiz katman sistemi ile maliyetleri optimize eder. Kullanıcılar ihtiyaçlarına göre en uygun ve maliyet etkin LLM sağlayıcısını seçebilir.

5. **Bireysel Tek Seferlik $299 Fiyatlandırma**: Çoğu rakibin abonelik tabanlı modeline karşılık, ABS bireysel kullanıcılar için tek seferlik $299 fiyatlandırma sunar. Uzun vadede önemli maliyet avantajı + öngörülebilir yatırım.

6. **Kıdemli Yargıç ve Sonuç Takibi**: ABS, üretilen kodun kalitesini değerlendirmek ve sonuçları izlemek için "Senior Judge" mekanizması ve kapsamlı outcome tracking sunar. AI kodunun güvenilirliğini artırır.

7. **Sembol Farkındalıklı RAG**: Sourcegraph Cody Enterprise ($59/kullanıcı/ay) gibi üst düzey rakiplerde bulunan sembol farkındalıklı RAG özelliği ABS'de de mevcuttur. Kod tabanını derinlemesine anlayarak daha alakalı öneriler.

8. **Dogfooding Güvenilirliği**: ABS, kendi geliştirme süreçlerimizde 6 aydan uzun süredir aktif kullanılmaktadır. Bu "dogfooding" yaklaşımı, ürünün gerçek dünya senaryolarında kanıtlanmış güvenilirliğini gösterir.

## 5. Neden ABS Seçilsin? (Değer Önermesi)

ABS, ekibinizin mevcut Claude Code deneyimini bozmadan, $20 Pro planıyla $1000+/ay enterprise seviyesine çıkarır. 75 MCP aracı, 6 sağlayıcılı kademeli maliyet optimizasyonu ve Türkçe kalite pipeline'ı gibi benzersiz özellikleriyle tek seferlik $299 fiyatlandırmasıyla, geliştirme süreçlerinizi dönüştürür.

## 6. Hedef Müşteri Profili

- **Claude Code Kullanıcıları**: Mevcut deneyimlerini geliştirmek isteyen bireysel geliştiriciler ve ekipler.
- **Ekibi Olanlar**: Birden fazla geliştiricinin birlikte çalıştığı küçük ve orta ölçekli ekipler.
- **Maliyet Duyarlı**: Yüksek abonelik ücretlerinden kaçınarak, uzun vadede maliyet etkin çözüm arayanlar.
- **TR-First veya Vendor-Agnostic İsteyenler**: Türkçe dil desteğine öncelik veren veya belirli bir bulut sağlayıcısına bağlı kalmak istemeyen ekipler.

## 7. Rekabet Etmeyeceğimiz Pazar

- **Düşük Kodlu (Low-Code) Platformlar**: Dify veya FlowiseAI'ın düşük kodlu uygulama geliştirme yetenekleri ABS'nin odak noktası değil.
- **Kurumsal Dev Çözümler**: GitHub Copilot Enterprise veya Amazon Q Developer Enterprise gibi devasa kurumsal entegrasyonlarla doğrudan rekabet etmiyoruz.
- **Sadece Bulut Tabanlı Çözümler**: Cursor gibi tamamen cloud-bound veya IDE'ye sıkıca bağlı çözümlerden farklı olarak, ABS self-host imkanı sunar.

---

Positioning statement'ı `marketing/landing-hero.md`'ye taşınacak.
