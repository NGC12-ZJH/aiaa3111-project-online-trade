# 商品品类人工标注指南（金标准 · taxonomy_v1_rc1）

> 版本：taxonomy_v1_rc1（冻结于 2026-11-12T13:59:48+00:00）· 由 `experiments/b_taxonomy/make_annotation_guide.py` 生成 · 负责人：B（Jinghan ZHAO）

## 1. 你要做什么

- 给 **200 个商品**各选一个“子类”。这 200 个商品是随机抽出的“金标准”，用来检验电脑自动标签（关键词规则和 LLM）准不准。
- 两位标注人（A、D）**各自独立**标注同一批商品，C 裁定两人不一致的地方。
- 预计用时 **1–1.5 小时**。每个商品通常几秒就能判断，难的可以上网搜图。
- 文件：`data/taxonomy/gold/gold_annotation_A.xlsx`（A 用）或 `gold_annotation_D.xlsx`（D 用）。两份的商品相同，但顺序不同。

## 2. 盲标纪律（很重要）

为了让金标准真正独立，标注时请：

1. **只看这份指南和你自己的 Excel。**
2. **不要打开仓库里 `data/taxonomy/` 和 `experiments/b_taxonomy/results/` 下的其他文件**。里面有电脑给这些商品打的标签（v0、LLM 的 R1–R3 等），看了就不再是独立判断了。
3. **标完之前不要和另一位标注人讨论**，也不要互看文件。
4. 不要修改“编码”和“商品写法”两列，也不要增删行或调整顺序。

## 3. Excel 怎么填

| 列 | 怎么填 |
|---|---|
| 序号、商品编码、商品写法 | 已填好，不要改。“商品写法”里用竖线分隔的，是同一个商品的不同写法 |
| **子类代码** | 点单元格右侧的小箭头，从下拉菜单里选一个（菜单内容 = 第 6 节的 77 个代码，含 other）。也可以直接输入代码 |
| 子类中文名 | 自动显示，用来核对有没有选错；不用填 |
| 不确定 | 拿不准就选“是”，有把握就留空 |
| 第二选择 | 只在“不确定”时填，同样从下拉菜单选 |
| 备注 | 可选。例如“搜图后发现是 xx”“两类都说得通，因为……” |

Excel 里还有两张表：“类别清单”（与第 6 节相同，可筛选）和“标注规则”（第 4 节的简版）。WPS 和 Excel 都能用；如果下拉菜单不显示，直接输入代码即可。

## 4. 判断原则

1. **按“它是什么东西、拿来做什么”判断**。颜色、图案、尺寸、材质、节日、主题和设计系列都不改变子类。例如圣诞图案的茶蜡座仍然是烛台，RETROSPOT 波点的挂钟仍然是时钟。
2. **看商品名里的“主体名词”**。商品名通常是“修饰词 + 主体”，主体决定子类。例如 BLACK BAROQUE WALL CLOCK 的主体是 WALL CLOCK（挂钟），BAROQUE 只是风格；GREEN ROSE CUSHION COVER 的主体是 CUSHION COVER（靠垫套），ROSE 只是图案。
3. **成套商品按套装里的商品判断**。“SET OF 6 ...”“S/3 ...”按套装里的商品归类（例如 6 个茶蜡一套仍是茶蜡）。带礼盒的商品请按第 6 节“礼品盒”的定义判断；拿不准就按原则 7 处理。
4. **一物多用时，选它最主要的用途**。例如带挂钩的墙面收纳板，主要用来收纳，就选挂钩搁板类，而不是黑板。实在分不清主次，就选你认为最可能的，并勾“不确定”。
5. **节日商品和普通商品同样处理**。圣诞、复活节、情人节、万圣节的商品按商品类型归入普通子类。节日已由系统另外记录，不需要在这里体现。
6. **可以上网搜商品名看图片**。用英文商品名搜索图片，帮助判断是什么东西（这家零售商的商品在网上很常见）。但不要查看本项目仓库里任何已有的标签文件（见第 2 节）。
7. **拿不准时：先选，再标“不确定”，写第二选择**。不要因为拿不准就选 other。选最接近的子类，在“不确定”一栏填“是”，并在“第二选择”填另一个候选。
8. **other 只在确实看不懂或不是商品时用**。例如完全无法理解的缩写、邮费、手续费等。

## 5. 常见缩写

商品名经常缩写或被截断：

- ASS / ASSTD / ASSORTED = assorted designs or colours
- COL = colour; DES = design
- T-LIGHT / TLIGHT / T LIGHT = tea light (small candle); HLDR / HOLDR = holder
- S/2, S/3, SET/3, SET/6 = set of 2, 3, 6
- SML / LGE / MED = small / large / medium
- P'WEIGHT = paperweight; B'FLY = butterfly; C/COVER = cushion cover
- DEC / DECORATION = decoration (usually a hanging or standing ornament)
- XMAS = Christmas; HOTTIE = hot water bottle
- VINT = vintage; ANT = antique; 50'S = 1950s style
- W/ = with; + = and

## 6. 子类清单（10 个大类、76 个子类，外加 other）

每个子类给出：代码、中文名、“是什么”、“包括”、“不包括”，以及 3 个真实商品作例子（例子都不在这 200 个商品里）。

### 个人护理与手工（personal_care，3 个子类）

| 代码 | 中文名 | 是什么 | 包括 | 不包括 | 例子 |
|---|---|---|---|---|---|
| `bath_beauty` | 洗浴美容用品 | 洗澡淋浴时用的个人护理用品 | 毛巾浴巾、皂托、沐浴海绵等浴室用品 | 厨房纺织品（kitchen_textiles）、纸巾（tissues_plasters） | SOFT PINK ROSE TOWEL; LARGE CAKE TOWEL PINK SPOTS; FAIRY SOAP SOAP HOLDER |
| `sewing_craft` | 缝纫和手工艺套装 | 缝纫、毛毡手工等手作项目用的套件和材料 | 缝纫套件、毛毡娃娃套件、编织套件、纽扣等 | 美术用品（pens_pencils_art）、做好的纺织成品 | VICTORIAN SEWING KIT; BASKET OF FLOWERS SEWING KIT; MIDNIGHT GLAMOUR SCARF KNITTING KIT |
| `tissues_plasters` | 纸巾和创可贴 | 一次性纸巾和急救创可贴 | 随身纸巾包、创可贴 | 沐浴海绵（bath_beauty）、厨房毛巾（kitchen_textiles） | PACK OF 12 RED SPOTTY TISSUES; PLASTERS IN TIN SKULLS; WHITE TISSUE REAM |

### 包袋（bags，6 个子类）

| 代码 | 中文名 | 是什么 | 包括 | 不包括 | 例子 |
|---|---|---|---|---|---|
| `fashion_handbags` | 时尚手袋 | 作为个人配饰随身携带的手袋、单肩包、晚宴包、腰包等小型时尚包 | 儿童卡通包；CHARLOTTE BAG | 化妆/洗漱包、旅行包、购物袋、收纳袋 | PINK STRIPES SHOULDER BAG; GREY FLORAL FELTCRAFT SHOULDER BAG; PINK DISCO HANDBAG |
| `household_laundry_storage` | 家居洗衣收纳 | 家务整理、洗衣、回收用的袋子、篮子和折叠工具 | 衣夹袋（PEG BAG）、抽绳袋、回收袋、叠衣板、洗衣篮 | 礼品袋、时尚包、化妆包、旅行包、购物袋 | RED SPOTTY PEG BAG; ENGLISH ROSE DESIGN PEG BAG; PEG BAG APPLES DESIGN |
| `jumbo_shopper_bag` | 大号购物袋 | 可重复使用、用于购物和装货的大号袋子 | 棉布或布料购物袋（SHOPPER、JUMBO BAG） | 午餐包（lunch_bag）、旅行包（travel_bags_luggage） | RED SPOTTY SHOPPER BAG; MODERN VINTAGE COTTON SHOPPING BAG; JUMBO BAG PINK WITH WHITE SPOTS |
| `lunch_bag` | 午餐包 | 装便当和零食的袋子（保温或不保温） | 带提手或拉链的午餐包 | 购物袋（jumbo_shopper_bag）、午餐盒（lunch_box_cutlery） | LUNCH BAG RED SPOTTY; LUNCH BAG WOODLAND; LUNCH BAG CARS BLUE |
| `travel_bags_luggage` | 旅行、野餐与沙滩包 | 旅行用的包和箱，也包括野餐包、沙滩包 | 登机包、旅行包、野餐包、沙滩包 | 购物袋（jumbo_shopper_bag）、午餐包（lunch_bag） | PINK VINTAGE PAISLEY PICNIC BAG; CABIN BAG VINTAGE RETROSPOT; AIRLINE BAG VINTAGE JET SET RED |
| `wash_cosmetic_bags` | 洗漱化妆包 | 装洗漱用品、化妆品和个人护理小物的拉链包或小袋 | 洗漱包、化妆包、洗漱小袋 | 钱包（purse_wallet）、抽绳袋或洗衣袋（household_laundry_storage） | GOLD WASHBAG; PINK ROSE WASHBAG; PINK BUTTERFLY WASHBAG |

### 厨房餐饮（kitchen_dining，14 个子类）

| 代码 | 中文名 | 是什么 | 包括 | 不包括 | 例子 |
|---|---|---|---|---|---|
| `baking_tools` | 烘焙工具和模具 | 烘焙用具 | 蛋糕模、烤盘、模具、饼干模 | 一般厨房用具（kitchen_tools）、一次性纸托（cake_cases） | ROUND CAKE TIN VINTAGE RED; SET OF 3 BUTTERFLY COOKIE CUTTERS; TEATIME CAKE TIN WITH HANDLE |
| `bowls` | 碗 | 盛放或食用食物的开口圆形容器 | 所有碗形的食物器皿，即使是装饰性的（果盘碗、圣代杯、洗手碗、布丁碗） | 盘子、平盘、托盘、宠物碗（pet_items） | BLUE SPOTTY PUDDING BOWL; GREEN SPOTTY BOWL; LARGE CHUNKY GLASS ROMAN BOWL |
| `cake_stand` | 蛋糕架 | 展示和端上蛋糕甜点的高脚盘或架子 | 玻璃、金属、陶瓷蛋糕架 | 一般的盘子（plates）、桌面摆件（tabletop_decorations） | GLASS CAKE STAND; RETRO SPOT CAKE STAND; VINTAGE METAL CAKE STAND CREAM |
| `coasters_placemats` | 杯垫和餐垫 | 垫在饮料或餐具下面保护桌面的小垫子 | 所有杯垫和餐垫，不论材质和图案 | 托盘、桌布 | SET OF 4 FAIRY CAKES COASTERS; FLOWERS TILE COASTER; S/4 PISTACHIO LOVEBIRD COASTERS |
| `egg_cups` | 蛋杯和蛋套 | 让煮鸡蛋立住的蛋杯，或给鸡蛋保温的蛋套 | 蛋杯、针织或毛毡蛋套 | 一般厨房工具（kitchen_tools）、餐具（plates） | PINK KNITTED EGG COSY; FELT EGG COSY CHICKEN; CREAM KNITTED HEN |
| `kitchen_storage` | 厨房储物罐 | 存放食物或厨房物品的铁盒、罐子、面包箱等容器 | 饼干铁盒、玻璃罐、面包箱 | 装饰收纳盒（trinket_jewellery_box）、篮子（storage_baskets_decor） | RED SPOTTY BISCUIT TIN; BREAD BIN DINER STYLE MINT; JARDIN ETCHED GLASS LARGE BELL JAR |
| `kitchen_textiles` | 厨房与餐桌纺织品 | 厨房和餐桌用的布艺品 | 茶巾、围裙、隔热手套、桌布、桌旗、布餐巾 | 纸巾（party_tableware）、浴巾（bath_beauty）、靠垫（cushions_textiles） | TEA TIME KITCHEN APRON; BLUE TEA TOWEL CLASSIC DESIGN; SET OF 2 FANCY FONT TEA TOWELS |
| `kitchen_tools` | 厨房工具和餐具 | 做饭、上菜或吃饭用的手持工具和餐具 | 勺子、锅铲、筷子、小锅 | 烘焙专用工具（baking_tools）、厨房储物（kitchen_storage）、盘子杯子等餐具（plates、mugs_cups） | RED EGG SPOON; RED PUDDING SPOON; SET OF 6 DOTS CHOPSTICKS |
| `lunch_box_cutlery` | 午餐盒和餐具套装 | 装便当的饭盒，常配迷你餐具 | 带餐具的饭盒、单独的迷你餐具套装 | 午餐包（lunch_bag）、正常尺寸的厨房用具（kitchen_tools） | LUNCHBOX WITH CUTLERY RETROSPOT; BLUE 3 PIECE MINI DOTS CUTLERY SET; DINOSAUR LUNCHBOX WITH CUTLERY |
| `mugs_cups` | 杯子和马克杯 | 喝茶、咖啡等热饮的杯子 | 马克杯、咖啡杯、杯碟、饮用玻璃杯 | 茶壶/咖啡壶（teapot_tea_set）、一次性纸杯（party_tableware） | RED SPOTTY COFFEE MUG; ORANGE FLOWER MUG; POTTERING MUG |
| `plates` | 盘子 | 盛放或食用食物的平盘或浅盘 | 餐盘、蛋糕盘、比萨盘 | 蛋糕架（cake_stand）、一次性纸盘（party_tableware） | RED SPOTTY PLATE; PIZZA PLATE IN BOX; CAKE PLATE LOVEBIRD WHITE |
| `serving_trays_platters` | 托盘和浅盘 | 带把手或边沿、用来端送或摆放多份食物的大托盘和浅盘 | 托盘、大浅盘、电视餐托盘（包括带支架的电视托盘桌） | 单人盘、碗、餐桌配件套装 | TV DINNER TRAY VINTAGE PAISLEY; RETRO PLASTIC 70'S TRAY; BLUE & WHITE BREAKFAST TRAY |
| `tableware_sets` | 餐桌配件与套装 | 布置餐桌用的装饰配件 | 餐巾环、餐巾扣、席位卡座等餐位装饰 | 盘子和餐具本身（plates、kitchen_tools）、派对餐具 | SET OF 4 NAPKIN CHARMS HEARTS; SCANDINAVIAN 3 HEARTS NAPKIN RING; 12 PINK ROSE PEG PLACE SETTINGS |
| `teapot_tea_set` | 茶壶和茶/咖啡套装 | 茶壶、咖啡壶、茶具套装，以及配套的下午茶器具 | 茶壶、咖啡壶、多件套茶具、奶壶、糖罐、茶叶罐 | 单只马克杯和杯碟（mugs_cups）、一般食品铁盒（kitchen_storage） | VINTAGE GLASS TEA CADDY; WHITE TEA,COFFEE,SUGAR JARS; FUNKY FLOWER COFFEE POT |

### 园艺户外（garden_outdoor，2 个子类）

| 代码 | 中文名 | 是什么 | 包括 | 不包括 | 例子 |
|---|---|---|---|---|---|
| `garden_outdoor` | 花园户外装饰 | 花园和户外空间用的装饰品和实用品 | 鸟屋、植物笼、花园标牌、园艺工具、户外摆件和花架 | 室内花瓶花盆（vases_planters）、宠物碗（pet_items） | BIRDHOUSE GARDEN MARKER; MINATURE COLOURED GARDENING SET; ENCHANTED BIRD PLANT CAGE |
| `pet_items` | 宠物碗和用品 | 宠物用品，主要是喂食碗及相关配件 | 狗碗、猫碗 | 人用的厨房储物（kitchen_storage）、花园装饰（garden_outdoor） | PINK DOG BOWL; CAT BOWL; DOG BOWL , CHASING BALL DESIGN |

### 家居装饰（home_decor，21 个子类）

| 代码 | 中文名 | 是什么 | 包括 | 不包括 | 例子 |
|---|---|---|---|---|---|
| `artificial_flowers` | 人造花卉 | 装饰用的人造花、花枝和花串 | 人造花、花签、花环串（LEI） | 鲜花、盆栽活植物 | RED POPPY ARTIFICIAL FLOWER; LARGE WHITE/PINK ROSE ART FLOWER; PURPLE FOXGLOVE ARTIIFCIAL FLOWER |
| `chalkboards_memo_boards` | 黑板和备忘板 | 可反复书写的黑板、粉笔板、备忘板（带或不带画架） | 纯书写用的板 | 主要功能是带挂钩/口袋的收纳板（hooks_racks_shelves）；印有文字的装饰标牌（wall_signs） | NATURAL SLATE CHALKBOARD LARGE; HOME SWEET HOME BLACKBOARD; BEACH HUT DESIGN BLACKBOARD |
| `clocks` | 时钟 | 挂墙或摆在桌上展示的时钟 | 挂钟、座钟 | 不作装饰用的手表或闹钟 | WHITE BAROQUE WALL CLOCK; BLACK DINER WALL CLOCK; BLACK SQUARE TABLE CLOCK |
| `cushions_textiles` | 靠垫与靠垫套 | 靠垫、靠垫套和其他软装纺织品 | 带芯靠垫、靠垫套、盖毯 | 厨房和餐桌纺织品（kitchen_textiles）、浴巾（bath_beauty）、热水袋（hot_water_bottle）、门挡（doorstops_paperweights） | PINK PAISLEY CUSHION COVER; GREEN ROSE CUSHION COVER; GOLD FLOWER CUSHION COVER |
| `door_hangers_signs` | 门牌、门挂与数字牌 | 用于标识或展示的门牌、数字/字母砖和门挂 | 数字砖、字母砖、门牌 | 墙面装饰画（wall_art）、悬挂装饰（hanging_ornaments） | NUMBER TILE VINTAGE FONT 0; FRENCH BLUE METAL DOOR SIGN, 0; CHARLIE+LOLA MY ROOM DOOR SIGN |
| `doormats` | 门垫 | 放在门口擦鞋、保护地面的垫子 | 室内外门垫 | 浴室地垫、宠物垫 | DOOR MAT RED SPOT; DOORMAT WELCOME TO OUR HOME; DOORMAT HOME SWEET HOME BLUE |
| `doorstops_paperweights` | 门挡和镇纸 | 有重量、用来抵住门或压住纸张的物件 | 装饰门挡、镇纸 | 不是按压重物设计的桌面摆件（tabletop_decorations） | SPOTTY PINK DUCK DOORSTOP; OWL DOORSTOP; SPOTTY CAT DOORSTOP |
| `furniture_knobs` | 家具与抽屉把手 | 小件家具，以及抽屉把手等家具五金 | 柜子、抽屉柜、边桌/茶几/咖啡桌、抽屉把手和拉手 | 墙面搁板和挂钩（hooks_racks_shelves）、收纳篮（storage_baskets_decor）、桌布（kitchen_textiles）、电视托盘桌（serving_trays_platters） | WOOD 2 DRAWER CABINET WHITE FINISH; EDWARDIAN 2 DRAWER WALL CABINET; WHITE SWEETHEARTS CABINET 4 DRAWERS |
| `hanging_ornaments` | 悬挂装饰（含圣诞树挂饰） | 设计成挂在树、枝条、钩子、窗户或墙上的装饰，不分季节 | 圣诞树挂饰、彩球（BAUBLE）、悬挂的心形/星形/小鸟装饰、吊饰（MOBILE） | 彩旗花环（bunting_garland）、花环（wreaths）、可独立摆放的摆件（tabletop_decorations）、悬挂式烛台（candle_holder_lantern）。节日另行记录，不影响子类 | HEART WOODEN CHRISTMAS DECORATION; PINK STAR CHRISTMAS DECORATION; PINK FEATHER CHRISTMAS DECORATION |
| `hooks_racks_shelves` | 挂钩、挂架和搁板 | 挂在墙上或悬挂的五金件，用来挂放和收纳外套、钥匙、杂志等 | 衣帽钩、搁板、杂志架、带挂钩或口袋的墙面收纳板 | 落地柜（furniture_knobs）、门挡 | CREAM SWEETHEART SHELF + HOOKS; FLOWERS TILE HOOK; DECORATIVE HANGING SHELVING UNIT |
| `hot_water_bottle` | 热水袋 | 灌热水取暖的热水袋，常带布套 | 带套热水袋（HOTTIE） | 暖手宝（hand_warmer）、靠垫 | PINK STRIPE HOT WATER BOTTLE; PINK HEART DOTS HOT WATER BOTTLE; SILVER SKULL HOT WATER BOTTLE |
| `mirrors` | 镜子 | 用来照自己的镜子 | 挂墙镜、手持镜、随身小镜 | 相框（photo_frame_album）、镜面墙饰（wall_art） | PINK OVAL JEWELLED MIRROR; ARCHED GREY MIRROR; GREEN ROUND COMPACT MIRROR |
| `photo_frame_album` | 相框和相册 | 展示照片的相框和收纳照片的相册 | 相框、相册 | 镜子（mirrors）、墙面装饰画（wall_art） | GOLD PHOTO FRAME; PINK JEWELLED PHOTO FRAME; BLACK GRAND BAROQUE PHOTO FRAME |
| `storage_baskets_decor` | 装饰收纳篮与玩具收纳 | 用于收纳或陈列的编织、柳条、木质或布质篮子、箱子和收纳筐 | 收纳篮、野餐篮、套篮、木箱、玩具收纳 | 洗衣袋和衣夹袋（household_laundry_storage）、食品铁盒和罐子（kitchen_storage）、小饰品盒（trinket_jewellery_box） | SET OF 3 BLUE STRIPE BASKET; PICNIC BASKET WICKER SMALL; FAIRY CAKE WICKER PICNIC BASKET |
| `tabletop_decorations` | 桌面装饰 | 摆在桌子、架子或壁炉台上的独立小摆件 | 小雕像、人偶、小型节日摆件 | 悬挂装饰（hanging_ornaments）、烛台（candle_holder_lantern） | BIRD DECORATION RED SPOT; WHITE/PINK CHICK EASTER DECORATION; GREEN GOOSE FEATHER CHRISTMAS TREE |
| `trinket_jewellery_box` | 首饰盒与小饰品盒 | 装首饰和小物件的装饰小盒、小罐、小托盘 | 首饰盒、小饰品罐（TRINKET POT）、小饰品托盘、首饰架、针线盒、纸巾盒 | 礼品盒（gift_boxes）、食品铁盒和罐子（kitchen_storage）、收纳篮（storage_baskets_decor） | GOLD JEWELERY BOX; RED POLKA DOT TISSUE BOX; VICTORIAN SEWING BOX MEDIUM |
| `vases_planters` | 花瓶和花盆 | 插花或种植物用的花瓶、小花插、花盆和种植器，包括挂墙和悬挂式 | 花瓶、小花插（POSY）、室内花盆、种植器 | 小饰品罐（trinket_jewellery_box）、花园装饰和工具（garden_outdoor）、烛台（candle_holder_lantern） | ZINC HEART LATTICE 2 WALL PLANTER; S/2 ZINC HEART DESIGN PLANTERS; CREAM WALL PLANTER HEART SHAPED |
| `wall_art` | 墙面装饰画与挂牌 | 挂在墙上的装饰品 | 墙面挂牌、镜面墙饰、装饰画 | 镜子（mirrors）、悬挂装饰（hanging_ornaments） | MIRRORED WALL ART POPPIES; FLOWERS AND BIRDS WALL PLAQUE; FRUIT TREE AND BIRDS WALL PLAQUE |
| `wall_signs` | 墙面标牌 | 印有文字或图案、挂墙或放在架子上的装饰或趣味标牌 | 金属标牌、日历牌、带单个挂钩的标牌（标牌是主体） | 门牌；黑板和备忘板；没有文字的装饰墙饰（wall_art） | PLEASE ONE PERSON METAL SIGN; WELCOME METAL SIGN; WASHROOM METAL SIGN |
| `word_blocks_letters` | 木质字母块 | 摆在架子、墙上或桌上的装饰木质字母或单词 | 可独立摆放或挂墙的木字母块 | 门牌（door_hangers_signs）、墙面装饰画（wall_art） | WELCOME WOODEN BLOCK LETTERS; PEACE WOODEN BLOCK LETTERS; JOY WOODEN BLOCK LETTERS |
| `wreaths` | 花环 | 用叶子、花、枝条等做成的环形装饰，通常挂在门上或墙上 | 所有名称含 WREATH 的商品，不论材质或季节 | 花环形的卡片架，以及不是用来展示的功能性物品 | WICKER WREATH SMALL; IVY HEART WREATH; GINGHAM HEART WREATH |

### 文具与礼品包装（stationery_gift_wrap，7 个子类）

| 代码 | 中文名 | 是什么 | 包括 | 不包括 | 例子 |
|---|---|---|---|---|---|
| `gift_boxes` | 礼品盒 | 用来包装礼物的装饰盒，有时里面附带小物件 | 预装小物的礼品盒 | 包装纸和标签（gift_wrap_tags）、装饰收纳盒（trinket_jewellery_box） | FAIRY CAKES RECTANGLUAR BOXES; PACK OF 6 SWEETIE GIFT BOXES; BLUE DIAMANTE PEN IN GIFT BOX |
| `gift_wrap_tags` | 礼品包装纸和标签 | 包装和标记礼物用的包装纸、胶带和标签 | 整卷或整张包装纸（WRAP）、礼品标签、包装胶带、丝带、礼品袋 | 礼品盒（gift_boxes）、贺卡（greeting_cards） | PINK SPOTS WRAP; CURIOUS IMAGES GIFT WRAP SET; PINK PAISLEY ROSE GIFT WRAP |
| `greeting_cards` | 贺卡与明信片 | 节日或传达心意用的贺卡、明信片、便笺和信封 | 单张卡、卡片套装、明信片、便笺、信封 | 礼品标签（gift_wrap_tags）、卡牌游戏如 SNAP CARDS（games_puzzles）、卡片架（tabletop_decorations） | FOLK ART GREETING CARD,pack/12; VINTAGE CARAVAN GREETING CARD; FAIRY CAKE GREETINGS CARD |
| `magnets` | 冰箱贴 | 贴在冰箱或其他磁性表面上的装饰磁贴 | 成套或单个的冰箱贴 | 磁性挂钩或工具 | SET 5 MINI CHOCOLATE FRIDGE MAGNETS; BIG DOUGHNUT FRIDGE MAGNETS; ASSORTED CAKES FRIDGE MAGNETS |
| `notebooks_journals` | 笔记本和日记本 | 装订成册、用来书写、记笔记或画画的纸品 | 笔记本、日记本、速写本 | 贺卡、文具套装 | VINTAGE NOTEBOOK PINK FLOWER; DAISY SKETCHBOOK; GREEN FERN NOTEBOOK |
| `pens_pencils_art` | 笔和美术用品 | 书写和绘画工具及相关美术材料 | 铅笔、钢笔、圆珠笔、橡皮 | 笔记本（notebooks_journals）、手工套件（sewing_craft） | 36 PENCILS TUBE RED SPOTTY; PACK OF 12 COLOURED PENCILS; FLOWER PENCIL/RUBBER+5 MINI PENCILS |
| `stickers_tattoos` | 贴纸和纹身贴 | 装饰贴纸和临时纹身贴 | 纸质和立体贴纸 | 包装纸和标签（gift_wrap_tags）、冰箱贴（magnets） | ANIMAL STICKERS; 3D VINTAGE CHRISTMAS STICKERS; FLOWERS STICKERS |

### 服饰配件（fashion_accessories，7 个子类）

| 代码 | 中文名 | 是什么 | 包括 | 不包括 | 例子 |
|---|---|---|---|---|---|
| `clothing_slippers` | 服装、鞋袜与扇子 | 可穿戴的衣物和鞋袜，以及手持扇子 | 拖鞋、袜子、围巾、遮阳帽、儿童服装、围嘴、扇子 | 编织套件（sewing_craft）、袜子木偶（soft_toys）、雨具（umbrella_rainwear）、暖手宝（hand_warmer） | COSY SLIPPER SHOES LARGE GREEN; ASSORTED COLOURS SILK FAN; AFGHAN SLIPPER SOCK PAIR |
| `hair_accessories` | 发饰 | 用来固定或装饰头发的饰品 | 发夹、发卡、发梳、发箍、发绳 | 耳罩，以及不是用来打理头发的帽子 | BLUE BLOSSOM HAIR CLIP; PAIR BUTTERFLY HAIR CLIPS; WHITE ENAMEL FLOWER HAIR TIE |
| `hand_warmer` | 暖手宝 | 能发热、用来暖手的随身小物，常可重复使用 | 口袋暖手宝 | 手套和其他服装（clothing_slippers） | HAND WARMER RED RETROSPOT; HI TEC ALPINE HAND WARMER; LOVE HEART POCKET WARMER |
| `jewellery` | 珠宝首饰 | 戴在身上的时尚首饰 | 项链、手链、耳环、戒指、胸针、首饰套装 | 发饰、包挂/手机挂件、钥匙扣、首饰展示架 | RESIN NECKLACE W PASTEL BEADS; AMBER GLASS/SHELL/PEARL NECKLACE; AMBER CHUNKY GLASS+BEAD NECKLACE |
| `keyrings_tags` | 钥匙扣、包挂与行李牌 | 挂在钥匙、包、手机上的小配件，以及行李牌 | 钥匙扣、钥匙坠、包挂、手机挂件、行李牌 | 戴在身上的首饰（jewellery）、礼品标签（gift_wrap_tags） | AMBER BERTIE GLASS BEAD BAG CHARM; GREEN WITH METAL BAG CHARM; PINK BEADS+HAND PHONE CHARM |
| `purse_wallet` | 钱包 | 装钱和证件的钱包 | 钱包、零钱包、卡包、护照套 | 洗漱化妆包（wash_cosmetic_bags）、手袋（fashion_handbags）、钥匙扣（keyrings_tags） | RED SPOTTY PURSE; BLUE FLOWER DES PURSE; SILVER PURSE GOLD PINK BUTTERFLY |
| `umbrella_rainwear` | 雨伞、阳伞与雨具 | 雨伞、阳伞和雨具 | 折叠伞、装饰阳伞、雨披、雨帽 | 其他服装（clothing_slippers）、鸡尾酒纸伞（party_tableware） | VINTAGE PINK DECORATIVE PARASOL; FOLDING UMBRELLA , RED/WHITE SPOT; BLUE/BROWN DOTS RUFFLED UMBRELLA |

### 烘焙与派对（baking_party，4 个子类）

| 代码 | 中文名 | 是什么 | 包括 | 不包括 | 例子 |
|---|---|---|---|---|---|
| `bunting_garland` | 彩旗和花环 | 成串的彩旗或纸艺造型，用于节庆布置 | 纸质或布质花环（GARLAND）、彩旗（BUNTING）、纸链 | 单个的悬挂装饰（hanging_ornaments） | WHITE BELL HONEYCOMB PAPER GARLAND; 3D HEARTS HONEYCOMB PAPER GARLAND; MINI WOODEN HAPPY BIRTHDAY GARLAND |
| `cake_cases` | 蛋糕纸托 | 垫在蛋糕/松饼模具里的一次性纸托或锡箔托 | 烘焙纸托 | 可重复使用的蛋糕模（baking_tools）、纸巾和纸杯（party_tableware） | PACK OF 60 PINK PAISLEY CAKE CASES; 60 GOLD AND SILVER FAIRY CAKE CASES; 60 CAKE CASES VINTAGE CHRISTMAS |
| `party_bags_supplies` | 派对袋和派对用品 | 派对用的一次性或装饰性用品 | 派对礼品袋、气球、邀请卡、糖果筒等派对小物 | 派对餐具（party_tableware）、彩旗花环（bunting_garland） | 12 COLOURED PARTY BALLOONS; PINK PARTY BAGS; GIRLS PARTY BAG |
| `party_tableware` | 派对餐具 | 派对用的一次性纸质或塑料餐具 | 纸巾、纸盘、纸杯 | 可重复使用的盘子（plates）、派对袋和派对用品（party_bags_supplies） | SET/20 RED SPOTTY PAPER NAPKINS; SET/6 STRAWBERRY PAPER CUPS; SET/6 POSIES PAPER CUPS |

### 玩具（toys_kids，5 个子类）

| 代码 | 中文名 | 是什么 | 包括 | 不包括 | 例子 |
|---|---|---|---|---|---|
| `games_puzzles` | 游戏和拼图 | 桌面游戏、卡牌游戏、宾果、多米诺、拼图和拼图积木 | 经典或授权的卡牌/棋盘游戏、拼图 | 户外的保龄、槌球、飞盘等动作玩具；拼搭和人偶套装 | MINI JIGSAW DINOSAUR; JIGSAW TREE WITH BIRDHOUSE; JIGSAW TOADSTOOLS 3 PIECE |
| `money_boxes` | 存钱罐 | 存钱用的陶瓷、木质或趣味存钱罐 | 名称含 MONEY BOX、MONEY BANK、PIGGY BANK、COIN BANK 的商品 | 用于收纳的铁盒，即使可以叠放（kitchen_storage） | CERAMIC HEART FAIRY CAKE MONEY BANK; BLUE YELLOW FLOWER PIGGY BANK; CERAMIC STRAWBERRY MONEY BOX |
| `outdoor_active_toys` | 户外运动玩具 | 户外或需要活动身体的玩具 | 花园槌球、保龄瓶、飞盘、滑翔机、玩具直升机、风车、充气地球仪/球、跳绳、接球杯、陀螺等传统动作玩具 | 桌面棋盘/卡牌游戏、拼图 | SMALL RED SPOT WINDMILL; SMALL SKULL WINDMILL; FLOWER WINDMILL |
| `playsets_figurines` | 游戏套装和玩偶 | 小型玩偶、玩具屋房间套装和过家家工具套装 | 多件套动物/恐龙/爬虫套装、玩具屋家具、儿童角色扮演工具 | 毛绒玩具、棋盘/卡牌游戏、拼图、户外玩具 | EIGHT PIECE CREEPY CRAWLIE SET; POPPY'S PLAYHOUSE LIVINGROOM; ASSORTED CREEPY CRAWLIES |
| `soft_toys` | 毛绒玩具 | 填充、毛绒或软针织的玩具 | 名称含 SOFT TOY、TEDDY 的商品，毛绒或针织娃娃、软体动物 | 毛毡娃娃套件（sewing_craft）、娃娃或动物造型的门挡、存钱罐、FLYING DUCKS 这类墙面装饰 | GOLD TEDDY BEAR; FLORAL ELEPHANT SOFT TOY; STRIPES DESIGN MONKEY DOLL |

### 蜡烛与灯具（candles_lighting，7 个子类）

| 代码 | 中文名 | 是什么 | 包括 | 不包括 | 例子 |
|---|---|---|---|---|---|
| `candle_holder_lantern` | 烛台和灯笼 | 用来安全放置蜡烛或茶蜡的烛台、烛盘、灯笼 | 烛盘、茶蜡座（T-LIGHT HOLDER）、玻璃烛杯、灯笼 | 灯串（lights_lamps）、香座（incense） | FLUTED ANTIQUE CANDLE HOLDER; LIGHT PINK FLOCK GLASS CANDLEHOLDER; PINK GLASS CANDLEHOLDER |
| `decorative_candles` | 装饰造型蜡烛 | 用于观赏而非普通照明的蜡烛 | 造型或趣味蜡烛、装在装饰杯/茶杯里的蜡烛、鹅卵石或球形蜡烛、装饰蜡烛套装 | 茶蜡（tealight_candles）、餐用/锥形/柱形蜡烛（dinner_taper_pillar_candles）、罐装或铁盒装香薰蜡烛（scented_candles） | ORANGE CANDLE; RETRO SPOT CANDLE SMALL; LARGE WHITE CHOCOLATE CANDLE |
| `dinner_taper_pillar_candles` | 餐用/柱形/锥形蜡烛 | 插在烛台上用于用餐、教堂或一般照明的标准圆柱、锥形或柱形蜡烛 | 名称含 DINNER、TAPER、PILLAR、CHURCH、ADVENT 的蜡烛，以及标准圆形/方形/立方体蜡烛 | 茶蜡、造型蜡烛、容器装香薰蜡烛 | S/4 BLUE DINNER CANDLE SILVER FLOCK; BLACK FLOCK GOLD CANDLE; COLUMBIAN CANDLE ROUND |
| `incense` | 香与香薰配件 | 香（线香、锥香）以及其他不是蜡烛的居家香氛用品 | 香、香座、熏香炉、香薰油、香包、香和蜡烛的组合套装 | 各种蜡烛（四个蜡烛子类）、烛台（candle_holder_lantern） | ORIGAMI VANILLA INCENSE+FLOWER; ORIGAMI ROSE INCENSE/CANDLE SET; ORIGAMI LAVENDER INCENSE CONES |
| `lights_lamps` | 灯饰 | 照明或装饰用的灯具 | 灯串（FAIRY LIGHTS、CHERRY LIGHTS）、台灯、灯罩 | 烛台（candle_holder_lantern）、不通电的灯笼 | LIGHT PINK CHERRY LIGHTS; BLUE ORGANDY ROUND LAMPSHADE W BEA; IVORY ROSE LAMPSHADE |
| `scented_candles` | 香薰蜡烛 | 主打香味的蜡烛，通常装在玻璃杯、铁盒、罐子或盒子里 | 名称含 SCENT 或香味、且不属于茶蜡/餐用柱形蜡烛/造型蜡烛的蜡烛；香薰蜡烛礼盒 | 带香味的茶蜡也归茶蜡（tealight_candles） | F.FAIRY S/3 CANDLE/GLASS,LAVENDER; ROSE SCENT CANDLE IN JEWELLED BOX; S/3 ROSE GARDEN SCENT SQU CANDLE |
| `tealight_candles` | 茶蜡/蜡烛杯 | 装在小杯里的小茶蜡，通常成套出售 | 名称含 T-LIGHT、T-LIGHTS、TEA LIGHT 的蜡烛，不论有没有香味、什么造型 | 大蜡烛、餐用/柱形蜡烛、容器装香薰蜡烛 | SET/6 SILVER REINDEER T-LIGHTS; SET/9 CHRISTMAS T-LIGHTS SCENTED; SET/6 IVORY BIRD T-LIGHT CANDLES |

### 其他

| 代码 | 中文名 | 是什么 | 包括 | 不包括 |
|---|---|---|---|---|
| `other` | 其他 | 不是商品，或描述完全无法理解 | 只在确实无法判断是什么东西时使用 | 能看懂是什么、只是一时不确定归哪类的商品——请选最接近的子类并勾“不确定” |

## 7. 常见问题

- **两个子类看起来都对怎么办？** 先按第 4 节的原则 2（主体名词）和原则 4（主要用途）判断；还是分不清，就选一个，勾“不确定”，再填第二选择。这类商品正是我们最想知道人和电脑分歧在哪里的地方，如实标注就好。
- **商品名看不懂？** 先查第 5 节的缩写表，再上网搜图。确实无法判断时才选 other。
- **我觉得某个子类的定义本身有问题？** 照现在的定义标，然后在备注里写下你的意见。类别结构已经冻结，评测结束后再统一讨论修改。
- **标到一半能停吗？** 可以，保存 Excel 后下次接着标。

## 8. 交回

- 标完后把文件重命名为 `gold_labels_A.xlsx` 或 `gold_labels_D.xlsx` 发给 B，保持 .xlsx 格式。
- 建议 **11-14 前**交回（以组内约定为准），这样 B 能在 11-15 前算出准确率。
- C 收到两份后，裁定两人不一致的商品。
