/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

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
            <strong>Automatia BCN</strong> · Barcelona, Spain
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            GDPR compliant
          </p>
        </div>

        <nav aria-label="Product">
          <h3 className="text-sm font-semibold">Product</h3>
          <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
            <li>
              <a href="#features" className="hover:text-foreground">
                Features
              </a>
            </li>
            <li>
              <a href="#contact" className="hover:text-foreground">
                Contact
              </a>
            </li>
            <li>
              <a href="#faq" className="hover:text-foreground">
                FAQ
              </a>
            </li>
            <li>
              {/* abs.automatiabcn.com does not resolve — this link had been
                  dead. The install guide that exists is the one in the repo. */}
              <a
                href="https://github.com/automatiabcn/abs#quick-install-15-minutes"
                className="hover:text-foreground"
                rel="noreferrer"
                target="_blank"
              >
                Installation guide
              </a>
            </li>
          </ul>
        </nav>

        <nav aria-label="Contact and legal">
          <h3 className="text-sm font-semibold">Contact</h3>
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
                Terms of service
              </a>
            </li>
            <li>
              <a href="/privacy" className="hover:text-foreground">
                Privacy policy
              </a>
            </li>
          </ul>
        </nav>
      </div>

      <div className="mt-10 border-t border-border pt-6 text-xs text-muted-foreground">
        © {new Date().getFullYear()} Automatia BCN. All rights reserved.
      </div>
    </div>
  </footer>
);

export default Footer;
