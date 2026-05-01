import type { FC } from "react";

const Footer: FC = () => (
  <footer
    aria-labelledby="footer-title"
    className="border-t border-border bg-card/30"
  >
    <div className="container mx-auto px-4 py-12">
      <div className="grid grid-cols-1 gap-8 sm:grid-cols-3">
        <div>
          <h2 id="footer-title" className="text-base font-semibold">
            Automatia ABS
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            <strong>Automatia BCN</strong> · Barcelona, İspanya
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            GDPR uyumlu
          </p>
        </div>

        <nav aria-label="Ürün">
          <h3 className="text-sm font-semibold">Ürün</h3>
          <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
            <li>
              <a href="#features" className="hover:text-foreground">
                Özellikler
              </a>
            </li>
            <li>
              <a href="#contact" className="hover:text-foreground">
                İletişim
              </a>
            </li>
            <li>
              <a href="#faq" className="hover:text-foreground">
                SSS
              </a>
            </li>
            <li>
              <a
                href="https://abs.automatiabcn.com/docs/install"
                className="hover:text-foreground"
              >
                Kurulum rehberi
              </a>
            </li>
          </ul>
        </nav>

        <nav aria-label="İletişim ve yasal">
          <h3 className="text-sm font-semibold">İletişim</h3>
          <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
            <li>
              <a
                href="mailto:support@automatiabcn.com"
                className="hover:text-foreground"
              >
                support@automatiabcn.com
              </a>
            </li>
            <li>
              <a href="/terms" className="hover:text-foreground">
                Kullanım koşulları
              </a>
            </li>
            <li>
              <a href="/privacy" className="hover:text-foreground">
                Gizlilik politikası
              </a>
            </li>
          </ul>
        </nav>
      </div>

      <div className="mt-10 border-t border-border pt-6 text-xs text-muted-foreground">
        © {new Date().getFullYear()} Automatia BCN. Tüm hakları saklıdır.
      </div>
    </div>
  </footer>
);

export default Footer;
