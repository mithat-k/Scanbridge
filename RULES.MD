\# Scanbridge - Yapay Zeka Kurallar Kitabı (Anayasa)



Bu döküman, Scanbridge projesinin değişmez mimari, erişilebilirlik ve kod koruma yasalarını içerir. Üretilecek tüm kodlar bu kurallara %100 uymak zorundadır.



\## 1. Çekirdek ve Donanım Mimarisi

\- \*\*Teknoloji Yığını:\*\* Proje tamamen PyQt6 (Python 3.14+) ve asenkron QThread mimarisi üzerine kuruludur.

\- \*\*Donanım Hızlandırma:\*\* `health\_checker.py` asenkron çalışır; CUDA uyumlu GPU varsa otomatik tetiklenir, yoksa INT8 kuantizasyon ile CPU moduna sorunsuz geçer.

\- \*\*Bellek Yönetimi (Disk I/O Yasaktır):\*\* OCR sürecinde resimler kesinlikle diske yazılmamalıdır. Dönüşümler tamamen bellek içinde (In-Memory) `Pixmap -> PIL Image -> NumPy` akışıyla yapılmalıdır.

\- \*\*Model Önbelleği (Cache):\*\* EasyOCR ve Pix2Text modelleri sınıf düzeyinde (`\_reader`, `\_p2t`) önbellekte tutulur, oturum açıkken donanım değişmedikçe yeniden yüklenmez.



\## 2. Web Erişilebilirlik (A11Y) Standartları

\- \*\*Arayüz Odaklanması:\*\* Tüm kritik UI bileşenlerinde klavye navigasyonu için `Qt.FocusPolicy.StrongFocus` zorunludur.
Etkileşimli olmayan düz metin etiketlerine (`QLabel`), rozetlere veya ilerleme çubuklarına (`QProgressBar`) kesinlikle `Qt.FocusPolicy.StrongFocus` verme. `TAB` döngüsü yalnızca tıklanabilir butonları (`QPushButton`) hedeflemelidir. Bilgiler kullanıcıya zaten `QAccessible.Event.Alert` ile asenkron anons edilmektedir
\- \*\*Ekran Okuyucu Anonsları:\*\* Win32 ctypes yasaktır. NVDA/JAWS anonsları için PyQt6'nın yerleşik `QAccessible` ve `QAccessibleEvent` (Alert/NameChanged) mekanizması kullanılmalıdır.

\- \*\*HTML-to-HTML MathML Stratejisi:\*\* Akademik makalelerin tablo, sütun ve zengin mizanpaj hiyerarşisini korumak için döküman Markdown'a çevrilmez; doğrudan zengin HTML olarak kurgulanır. 

\- \*\*Pandoc Entegrasyonu:\*\* Formüller HTML içine `$$...$$` olarak gömülür. `pypandoc.convert\_text` motoru `format='html'`, `to='html'` ve `extra\_args=\['--mathml']` parametreleriyle çağrılarak sadece formüller semantik `<math>` etiketlerine dönüştürülür.



\## 3. Kod Koruma Kuralları (ASLA YAPMA)

\- \*\*Kural 1:\*\* EasyOCR (`easyocr.Reader`) başlatırken kesinlikle `workers` parametresini kullanma; çökmeye sebep olur.

\- \*\*Kural 2:\*\* Pix2Text `recognize\_page()` fonksiyonuna doğrudan PIL Image nesnesi verme, kabul etmez. Resmi geçici bir dosyaya yazıp dosya yolunu pasla, işlem bitince geçici dosyayı sil.

\- \*\*Kural 3:\*\* Pix2Text 1.0+ sürümlerinde çıktı bir `Page` nesnesidir ve doğrudan iterable değildir. Döngüye sokarken mutlaka `.elements` listesini hedefle.

\- \*\*Kural 4:\*\* `HealthCheckerWorker(QThread)` içinde kesinlikle `finished` adında bir sinyal tanımlama; QThread'in kendi yaşam döngüsü sinyalini ezdiği için kilitlenmeye sebep olur. Sinyal adını `result\_ready` yap.

\- \*\*Kural 5:\*\* OCR aşamasında araya sızan anlamsız karakter dizilerini ve her sayfada tekrarlayıp metni bölen soluk filigran yazılarını filtrele, DOM'a ekleme.

\- \*\*Kural 6:\*\* Ekran okuyucuların arka plandaki sayfaları aynı anda okumasını engellemek için aktif olmayan tüm sayfalara otomatik olarak `aria-hidden="true"` ve `style="display: none;"` niteliklerini enjekte et.
- *** 
- **Sistem Bağımlılığı Yasaktır:** Proje cross-platform olmak zorundadır. İşletim sistemine özel harici binary'ler  kesinlikle koda eklenemez. Her şey saf Python  ekosisteminde çözülmelidir.