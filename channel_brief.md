# Channel brief — вибір власника

> **16.11: назву обрано — Huge To Scale (`@HugeToScale`).** Пласкі банери та аватари з
> розділів 2–3 відхилено. Нові варіанти — 3D-рендер у Blender, лежать у `branding3d/final/`
> (див. розділ 6 унизу).

Формат: англомовні Shorts без голосу. Реальний великий об'єкт чи явище у знайомому місці в
реальному масштабі. 3D (Blender), CC0-музика, 1 Short на день о 19:00 за Києвом.

## 1. Назва каналу і handle

Перевірено 16.11.2026. Сторінка `youtube.com/@handle` відповідає 404, тобто каналу з таким
handle немає. Пошук каналів YouTube за назвою не знайшов жодного каналу з такою самою назвою.
Остаточно handle закріплюється лише в YouTube Studio, коли ви його вводите: зарезервований
handle звідси не видно.

| # | Назва | Handle | Чому |
|---|---|---|---|
| 1 | **Dropped To Scale** | `@DroppedToScale` | Описує сам формат: об'єкт «падає» в знайоме місце в реальному розмірі |
| 2 | **Huge To Scale** | `@HugeToScale` | Коротко і зрозуміло з першого слова; добре читається на аватарі й у пошуку |
| 3 | **Placed For Scale** | `@PlacedForScale` | Обіграє інтернет-звичку «___ for scale», нейтральна для будь-якого об'єкта |

Відкинуто, бо такі канали вже є: Sense of Scale (кілька каналів із цією назвою), Scale Check,
True Scale, Scale Shock, Size It Up, How Big Really.

## 2. Аватар (800×800 PNG, YouTube показує його колом)

На аватарах немає назви, тож будь-який підходить до будь-якої назви.

| Варіант | Файл | Що на ньому |
|---|---|---|
| A | `branding/out/avatar_A_bar.png` | Величезна жовта лінійка-стовп поруч із крихітною людиною, темно-фіолетовий фон |
| B | `branding/out/avatar_B_arrow.png` | Велетенська жовта стрілка «падає» поруч із людиною, синьо-фіолетовий градієнт |
| C | `branding/out/avatar_C_one_to_one.png` | Великий жовтий «1:1» з обводкою, лінійка й людина, рожево-помаранчеві промені |

## 3. Банер (2560×1440 PNG)

Текст стоїть у зоні 1546×423, яку видно на всіх пристроях. Файли `*_safearea.png` — лише
для перевірки: на них ця зона обведена зеленим.

| Варіант | Файл | Стиль |
|---|---|---|
| A | `branding/out/banner_A_dropped_to_scale.png` | Нічне місто, жовта лінійка-стовп, жовта назва |
| B | `branding/out/banner_B_huge_to_scale.png` | Синє небо, жовта стрілка, жовта назва |
| C | `branding/out/banner_C_placed_for_scale.png` | Захід сонця рожево-помаранчевий, лінійка, біла назва |

Будь-який стиль банера можна поєднати з будь-якою назвою. Він перемальовується однією командою:
`python branding/make_branding.py "Huge To Scale"`.

Як зроблено: уся графіка намальована з простих векторних фігур кодом (`branding/make_branding.py`,
Pillow). Без ШІ, без фото, без чужих логотипів і без силуетів реальних будівель. Шрифт —
Anton (SIL OFL 1.1, ліцензія в `assets/fonts/Anton-OFL.txt`). Кольори: жовтий #FFD60A,
помаранчевий #FF7A00, блакитний #00D1FF, малиновий #FF2E88, обводка #0C0E1C — ті самі буде
використано в підписах Shorts.

## 4. Опис каналу (англійською, до вставки в YouTube)

> How big is it really? We take real giants — ships, rockets, storms, craters, whole countries —
> and drop them into places you know, at their true size. Every Short is built in 3D from real
> measurements, checked against two independent sources, with no voice-over and no AI imagery.
> A new Short every day.
>
> Map data © OpenStreetMap contributors. Borders: Natural Earth. 3D sources and licences are
> listed under each Short.

(Атрибуція OSM тут для загального порядку; у кожному Short вона буде й в описі відео.)

## 5. Ключові слова каналу

`size comparison`, `scale comparison`, `real size`, `true size`, `how big is`, `3D comparison`,
`size of things`, `biggest ship`, `Titanic size`, `Saturn V`, `country size comparison`,
`true size of countries`, `sense of scale`, `shorts`

## Що потрібно від вас

1. Назва: 1, 2 чи 3 (або своя — перевірю handle).
2. Аватар: A, B чи C.
3. Банер: A, B чи C (з вибраною назвою).

Після вибору створю публічний репозиторій під цю назву і зроблю тестові кадри трьох пробних
Shorts із заміром часу рендеру.

## 6. Банер і аватар у 3D (Blender) — варіанти v2

Рендер: Blender 4.2.3 LTS, Cycles на CPU, OpenImageDenoise, освітлення HDRI з Poly Haven (CC0).
Глянцева підлога з відображенням. Усі об'єкти мають реальний масштаб: перед рендером скрипт
перевіряє, що висота кожної моделі збігається з реальною в межах 1 %. Моделі спрощені й
зроблені мною з примітивів. Джерела й ліцензії — `branding3d/sources.json`.
Назва — шрифтом Anton, з товстою темною обводкою, лише в безпечній зоні 1546×423.

| Варіант | Небо | Гігант | Поруч |
|---|---|---|---|
| A | яскраво-блакитне | Saturn V, 110.6 m | Статуя Свободи, Біг-Бен, Тадж-Махал, людина |
| B | світанкове тепле | Seawise Giant (найдовший корабель в історії), поставлений на корму, 458 m | Ейфелева вежа, піраміда Хеопса, Біг-Бен, Статуя Свободи, людина |
| C | бірюзове | Ейфелева вежа (вдень), 330 m | Статуя Свободи, Біг-Бен, Тадж-Махал, Пізанська вежа, піраміда, людина |

Файли: `branding3d/final/out/banner_X_final.png` (2560×1440), `banner_X_phone.png` (так
банер видно на телефоні), `banner_X_desktop.png`, `avatar_X_final.png` (800×800),
`avatar_X_circles.png` (коло 800 / 98 / 48 px).
Аватари: A — Saturn V і крихітна людина; B — корабель на кормі поруч з Ейфелевою вежею;
C — Ейфелева вежа поруч із Біг-Беном.

**Вибір 16.11:** банер A + аватар A (власник: «любий»). Файли для YouTube:
`branding3d/final/out/banner_A_final.png`, `branding3d/final/out/avatar_A_final.png`.
