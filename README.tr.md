# ABS Studio — sunucu

🇬🇧 [English](README.md) · 🇹🇷 **Türkçe** · 🇪🇸 [Español](README.es.md)

> ABS Studio'nun sunucu tarafı: editör senin makinende, bu senin VPS'inde çalışır,
> arada bize ait bir şey yoktur. Sağlayıcıları, erişimi, araçları ve faturalamayı
> bu taraf getirir. **Ayda $5**, yedi gün kartsız deneme, istediğin ay iptal.
>
> Editörü mü arıyorsun? [app.automatiabcn.com](https://app.automatiabcn.com/studio).

## Neden ayrı bir sunucu

Her şeyi dizüstünde tutan bir AI editörü belgelerinde arama yapamaz, geçen haftaki
toplantıyı hatırlayamaz ve tek bir sağlayıcının kötü bir günü olduğunda durur. Her
şeyi bir satıcıya gönderen editör bunları çözer — karşılığında kodunu satıcıya verir.

Bu üçüncü cevap: editör, sahibi sen olan bir sunucuyla konuşur.

- **6 sağlayıcı** arasında devre kesicili yönlendirme — birinin kesintisi seninki olmaz.
- **157 MCP aracı**: RAG hibrit erişim, judge persona ML, fullstack geliştirici modu,
  Türkçe kalite hattı.
- Tamamen **senin makinende**. Automatia sunucularına hiçbir şey ulaşmaz; dışarı çıkan
  tek şey, kendi anahtarınla kendi yaptığın sağlayıcı çağrılarıdır.

## Hızlı kurulum

Linux bir VPS (Hetzner CX22, ayda $5 yeter) ve Docker gerekir.

```bash
ssh root@vps-ip
curl -fsSLO https://app.automatiabcn.com/download   # sunucu arşivi
tar -xzf abs-server-*.tar.gz && cd abs-server-*
./install.sh                                        # .env yazar, sonra tekrar çalıştır
```

İlk koşu senin dolduracağın bir `.env` üretir — alan adın ve bir yönetici adresi —
ikinci koşu yayınlanmış imajları çeker ve her şeyi Caddy'nin arkasında başlatır;
sertifikayı Caddy kendi alır. Kaynaktan hiçbir şey derlenmez, ilk yedi gün lisans
anahtarı istemez.

Detay: [Kurulum Rehberi](docs/setup-guide.md) ·
[Fiyatlandırma](https://app.automatiabcn.com/pricing)
