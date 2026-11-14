# dsh-superagent'tan uyarlanan tasarim

Kairo'nun "Superajan / is emirleri" ozelligi dsh-superagent'in tasarimindan uyarlanmistir.
Kod KOPYALANMADI; kavramlar (is emri, atama, yetki, asama tablosu, "az insan dikkati" ilkesi,
isci talimatindaki kurallar) Windows'ta calisacak sekilde Python'da yeniden yazildi:

- `app/agent/superajan.py` (is emri modeli, asama tablosu, isci talimati, depo)
- `app/api.py` (`/api/superajan` rotalari, `_superajan_tick`)
- `app/web/superajan.js` (yalniz insan bekleyenleri one cikaran panel)

Kaynak: https://github.com/deepseek-ai/dsh-superagent-prototype

MIT License. Copyright (c) 2026 DeepSeek Harness Team.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions: The above copyright notice and this
permission notice shall be included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
