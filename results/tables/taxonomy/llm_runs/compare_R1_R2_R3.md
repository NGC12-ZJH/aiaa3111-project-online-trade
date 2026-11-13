# LLM 打标签轮次比较：R1, R2, R3

> `compare_runs.py` 生成；不需要人工标签。一致率不是准确率，准确率要等人工金标准。

## 各轮概况

| 轮次 | 商品数 | 不合法 | other（按商品） | other（按购买加权） | 置信度中位数 | 置信度 < 0.7 | 新花费（美元） |
|---|---|---|---|---|---|---|---|
| R1 | 200 | 0 | 1.5% | 0.0% | 0.98 | 0 | 0.523 |
| R2 | 200 | 0 | 2.0% | 0.4% | 0.95 | 8 | 0.660 |
| R3 | 200 | 1 | 1.5% | 0.0% | 0.98 | 0 | 0.010 |

## 轮次两两一致率（子类 L2 / 大类 L1）

| 比较 | L2 一致 | L1 一致 | L2 一致（热门 100） | L2 一致（长尾 100） |
|---|---|---|---|---|
| R1 vs R2 | 86.0% | 89.5% | 86.0% | 86.0% |
| R1 vs R3 | 98.0% | 98.0% | 98.0% | 98.0% |
| R2 vs R3 | 85.5% | 89.0% | 86.0% | 85.0% |

**预先写定的检查：R1 vs R3 子类一致率 ≥ 85% → 通过 ✅**

## 与 v0 对照（只作参考，v0 未经验证）

| 轮次 | L1 一致 | L2 一致（只算 v1 中沿用 v0 id 的子类） |
|---|---|---|
| R1 | 83.0% | 89.2%（n=120） |
| R2 | 77.5% | 76.7%（n=120） |
| R3 | 84.5% | 90.1%（n=121） |

## R1 vs R2：不一致的商品（共 28 个）

| 编码 | 商品名 | R1 | R2 |
|---|---|---|---|
| 21114 | LAVENDER SCENTED FABRIC HEART | hanging_ornaments | incense |
| 21121 | SET/10 RED SPOTTY PARTY CANDLES | party_bags_supplies | decorative_candles |
| 21122 | SET/10 PINK SPOTTY PARTY CANDLES | party_bags_supplies | decorative_candles |
| 21208 | PASTEL COLOUR HONEYCOMB FAN | bunting_garland | party_bags_supplies |
| 21209 | MULTICOLOUR HONEYCOMB FAN | bunting_garland | hanging_ornaments |
| 21222 | SET/4 BADGES BEETLES | party_bags_supplies | jewellery |
| 21329 | DINOSAURS WRITING SET | notebooks_journals | greeting_cards |
| 21592 | RETRO SPOT CIGAR BOX MATCHES | trinket_jewellery_box | other |
| 21717 | EASTER TIN BUCKET | garden_outdoor | storage_baskets_decor |
| 22227 | DECORATION, HANGING HEART+MIRROR | mirrors | hanging_ornaments |
| 22297 | HEART IVORY TRELLIS SMALL | hanging_ornaments | garden_outdoor |
| 22344 | PARTY PIZZA DISH PINK WHITE SPOT | party_bags_supplies | plates |
| 22444 | GROW YOUR OWN PLANT IN A CAN | garden_outdoor | vases_planters |
| 22525 | CHILDRENS GARDEN GLOVES PINK | garden_outdoor | clothing_slippers |
| 22531 | MAGIC DRAWING SLATE CIRCUS PARADE | pens_pencils_art | chalkboards_memo_boards |
| 22567 | 20 DOLLY PEGS RETROSPOT | sewing_craft | household_laundry_storage |
| 22592 | CARDHOLDER HOLLY WREATH METAL | tabletop_decorations | tableware_sets |
| 22594 | CHRISTMAS GINGHAM TREE | tabletop_decorations | hanging_ornaments |
| 22622 | BOX OF VINTAGE ALPHABET BLOCKS | games_puzzles | word_blocks_letters |
| 22947 | WOODEN ADVENT CALENDAR RED | hanging_ornaments | tabletop_decorations |
| 23008 | DOLLY GIRL BABY GIFT SET | clothing_slippers | soft_toys |
| 23118 | PARISIENNE JEWELLERY DRAWER | furniture_knobs | trinket_jewellery_box |
| 47563B | WAVELINE SURF IRONING BOARD COVER | other | household_laundry_storage |
| 75013B | STRING OF 8 BUTTERFLIES,PINK | hanging_ornaments | bunting_garland |
| 84823 | DANISH ROSE FOLDING CHAIR | furniture_knobs | other |
| 84836 | ZINC METAL HEART DECORATION | hanging_ornaments | tabletop_decorations |
| 84946 | ANTIQUE SILVER TEA GLASS ETCHED | mugs_cups | candle_holder_lantern |
| 85089 | CANDY SPOT BUNNY | egg_cups | soft_toys |

## R1 vs R3：不一致的商品（共 4 个）

| 编码 | 商品名 | R1 | R3 |
|---|---|---|---|
| 21114 | LAVENDER SCENTED FABRIC HEART | hanging_ornaments | incense |
| 21703 | BAG 125g SWIRLY MARBLES | outdoor_active_toys | sewing_craft |
| 23008 | DOLLY GIRL BABY GIFT SET | clothing_slippers | other |
| 82011E | BATHROOM SCALES, FAG BREAK | other | kitchen_tools |

## R2 vs R3：不一致的商品（共 29 个）

| 编码 | 商品名 | R2 | R3 |
|---|---|---|---|
| 21121 | SET/10 RED SPOTTY PARTY CANDLES | decorative_candles | party_bags_supplies |
| 21122 | SET/10 PINK SPOTTY PARTY CANDLES | decorative_candles | party_bags_supplies |
| 21208 | PASTEL COLOUR HONEYCOMB FAN | party_bags_supplies | bunting_garland |
| 21209 | MULTICOLOUR HONEYCOMB FAN | hanging_ornaments | bunting_garland |
| 21222 | SET/4 BADGES BEETLES | jewellery | party_bags_supplies |
| 21329 | DINOSAURS WRITING SET | greeting_cards | notebooks_journals |
| 21592 | RETRO SPOT CIGAR BOX MATCHES | other | trinket_jewellery_box |
| 21703 | BAG 125g SWIRLY MARBLES | outdoor_active_toys | sewing_craft |
| 21717 | EASTER TIN BUCKET | storage_baskets_decor | garden_outdoor |
| 22227 | DECORATION, HANGING HEART+MIRROR | hanging_ornaments | mirrors |
| 22297 | HEART IVORY TRELLIS SMALL | garden_outdoor | hanging_ornaments |
| 22344 | PARTY PIZZA DISH PINK WHITE SPOT | plates | party_bags_supplies |
| 22444 | GROW YOUR OWN PLANT IN A CAN | vases_planters | garden_outdoor |
| 22525 | CHILDRENS GARDEN GLOVES PINK | clothing_slippers | garden_outdoor |
| 22531 | MAGIC DRAWING SLATE CIRCUS PARADE | chalkboards_memo_boards | pens_pencils_art |
| 22567 | 20 DOLLY PEGS RETROSPOT | household_laundry_storage | sewing_craft |
| 22592 | CARDHOLDER HOLLY WREATH METAL | tableware_sets | tabletop_decorations |
| 22594 | CHRISTMAS GINGHAM TREE | hanging_ornaments | tabletop_decorations |
| 22622 | BOX OF VINTAGE ALPHABET BLOCKS | word_blocks_letters | games_puzzles |
| 22947 | WOODEN ADVENT CALENDAR RED | tabletop_decorations | hanging_ornaments |
| 23008 | DOLLY GIRL BABY GIFT SET | soft_toys | other |
| 23118 | PARISIENNE JEWELLERY DRAWER | trinket_jewellery_box | furniture_knobs |
| 47563B | WAVELINE SURF IRONING BOARD COVER | household_laundry_storage | other |
| 75013B | STRING OF 8 BUTTERFLIES,PINK | bunting_garland | hanging_ornaments |
| 82011E | BATHROOM SCALES, FAG BREAK | other | kitchen_tools |
| 84823 | DANISH ROSE FOLDING CHAIR | other | furniture_knobs |
| 84836 | ZINC METAL HEART DECORATION | tabletop_decorations | hanging_ornaments |
| 84946 | ANTIQUE SILVER TEA GLASS ETCHED | candle_holder_lantern | mugs_cups |
| 85089 | CANDY SPOT BUNNY | soft_toys | egg_cups |