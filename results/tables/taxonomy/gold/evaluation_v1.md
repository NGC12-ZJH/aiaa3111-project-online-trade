# taxonomy_v1_rc1 金标准评测

> `evaluate_gold.py` 生成。金标准 200 个商品（A、D 独立盲标，C 裁定 15 个分歧），覆盖 61 个子类。准确率的 95% 置信区间用 Wilson 方法；n = 200 时区间宽约 ±5 个百分点。

## 1. 主表

| 方法 | 子类准确率 | 子类 95% CI | 大类准确率 | 子类宏平均 F1 | 按购买量加权子类准确率 | 热门 100 | 长尾 100 | 两人都确定的 146 个 | 有人不确定的 54 个 |
|---|---|---|---|---|---|---|---|---|---|
| v0 关键词规则 | **49.0%** | 42.2%–55.9% | 81.5% | 0.411 | 61.1% | 56.0% | 42.0% | 54.8% | 33.3% |
| R2 LLM 不给例子 | **90.0%** | 85.1%–93.4% | 92.5% | 0.880 | 93.1% | 91.0% | 89.0% | 98.6% | 66.7% |
| R1 LLM + 5 例子（主方法） | **87.0%** | 81.6%–91.0% | 90.5% | 0.823 | 91.4% | 88.0% | 86.0% | 97.3% | 59.3% |
| R3 换措辞（稳定性） | **87.0%** | 81.6%–91.0% | 90.5% | 0.824 | 91.3% | 88.0% | 86.0% | 97.3% | 59.3% |
| 标注人 A（参照） | **97.5%** | 94.3%–98.9% | 98.0% | 0.941 | 98.4% | 98.0% | 97.0% | 100.0% | 90.7% |
| 标注人 D（参照） | **94.5%** | 90.4%–96.9% | 96.0% | 0.936 | 95.2% | 94.0% | 95.0% | 100.0% | 79.6% |

- v0 只有旧的 53 个子类，在被拆分过的子类上必然答错。只看金标准子类仍沿用 v0 代码的 121 个商品，v0 子类准确率为 81.0%。
- 标注人 A、D 的准确率偏高（金标准就是由他们得出的），只作为“人能做到多好”的参照上限。

## 2. 两两比较（McNemar 精确检验）

| 比较 | 只有前者对 | 只有后者对 | p 值 |
|---|---|---|---|
| R1 vs R2（例子的作用） | 9 | 15 | 0.307 |
| R1 vs v0 | 77 | 1 | 5.23e-22 |

## 3. 按预先写定规则的结论

- 候选（v0、R2、R1）中子类准确率最高：**R2 LLM 不给例子**；与其相差 ≤ 2 个百分点的候选：R2 LLM 不给例子；按规则选出主方法：**R2 LLM 不给例子**。
- 主方法大类 92.5%、子类 90.0% → **达标，可以冻结（大类 ≥ 90%、子类 ≥ 80%）**。

## 4. R1 的错误（26 个）

| 编码 | 商品名 | 金标准 | R1 | 人是否确定 | 来源 | R1 备注 |
|---|---|---|---|---|---|---|
| 21114 | LAVENDER SCENTED FABRIC HEART | incense（香与香薰配件） | hanging_ornaments（悬挂装饰（含圣诞树挂饰）） | 有人不确定 | A=D |  |
| 21121 | SET/10 RED SPOTTY PARTY CANDLES | decorative_candles（装饰造型蜡烛） | party_bags_supplies（派对袋和派对用品） | 有人不确定 | A=D |  |
| 21122 | SET/10 PINK SPOTTY PARTY CANDLES | decorative_candles（装饰造型蜡烛） | party_bags_supplies（派对袋和派对用品） | 有人不确定 | A=D |  |
| 21222 | SET/4 BADGES BEETLES | jewellery（珠宝首饰） | party_bags_supplies（派对袋和派对用品） | 有人不确定 | A=D |  |
| 21329 | DINOSAURS WRITING SET | pens_pencils_art（笔和美术用品） | notebooks_journals（笔记本和日记本） | 有人不确定 | C=A |  |
| 21592 | RETRO SPOT CIGAR BOX MATCHES | candle_holder_lantern（烛台和灯笼） | trinket_jewellery_box（首饰盒与小饰品盒） | 有人不确定 | A=D |  |
| 21717 | EASTER TIN BUCKET | storage_baskets_decor（装饰收纳篮与玩具收纳） | garden_outdoor（花园户外装饰） | 有人不确定 | A=D | unparseable;retried |
| 22227 | DECORATION, HANGING HEART+MIRROR | hanging_ornaments（悬挂装饰（含圣诞树挂饰）） | mirrors（镜子） | 都确定 | A=D |  |
| 22344 | PARTY PIZZA DISH PINK WHITE SPOT | plates（盘子） | party_bags_supplies（派对袋和派对用品） | 都确定 | A=D |  |
| 22567 | 20 DOLLY PEGS RETROSPOT | household_laundry_storage（家居洗衣收纳） | sewing_craft（缝纫和手工艺套装） | 有人不确定 | A=D |  |
| 22594 | CHRISTMAS GINGHAM TREE | hanging_ornaments（悬挂装饰（含圣诞树挂饰）） | tabletop_decorations（桌面装饰） | 有人不确定 | A=D |  |
| 22603 | CHRISTMAS RETROSPOT TREE WOOD | tabletop_decorations（桌面装饰） | hanging_ornaments（悬挂装饰（含圣诞树挂饰）） | 有人不确定 | C=A |  |
| 22622 | BOX OF VINTAGE ALPHABET BLOCKS | word_blocks_letters（木质字母块） | games_puzzles（游戏和拼图） | 有人不确定 | C_third |  |
| 22750 | FELTCRAFT PRINCESS LOLA DOLL | soft_toys（毛绒玩具） | sewing_craft（缝纫和手工艺套装） | 有人不确定 | C=A |  |
| 22751 | FELTCRAFT PRINCESS OLIVIA DOLL | soft_toys（毛绒玩具） | sewing_craft（缝纫和手工艺套装） | 有人不确定 | C=A |  |
| 22947 | WOODEN ADVENT CALENDAR RED | tabletop_decorations（桌面装饰） | hanging_ornaments（悬挂装饰（含圣诞树挂饰）） | 有人不确定 | A=D |  |
| 23008 | DOLLY GIRL BABY GIFT SET | gift_boxes（礼品盒） | clothing_slippers（服装、鞋袜与扇子） | 有人不确定 | C=D |  |
| 23118 | PARISIENNE JEWELLERY DRAWER | trinket_jewellery_box（首饰盒与小饰品盒） | furniture_knobs（家具与抽屉把手） | 有人不确定 | A=D |  |
| 23143 | ZINC WIRE KITCHEN ORGANISER | kitchen_storage（厨房储物罐） | hooks_racks_shelves（挂钩、挂架和搁板） | 有人不确定 | C=A |  |
| 37112 | YELLOW BIRDS FELT DES FOODCOVER | kitchen_tools（厨房工具和餐具） | kitchen_textiles（厨房与餐桌纺织品） | 有人不确定 | C=D |  |
| 47503H | ASS FLORAL PRINT SPIRIT LEVEL | garden_outdoor（花园户外装饰） | other（其他） | 有人不确定 | C=A |  |
| 47563B | WAVELINE SURF IRONING BOARD COVER | household_laundry_storage（家居洗衣收纳） | other（其他） | 都确定 | A=D |  |
| 75013B | STRING OF 8 BUTTERFLIES,PINK | bunting_garland（彩旗和花环） | hanging_ornaments（悬挂装饰（含圣诞树挂饰）） | 有人不确定 | A=D |  |
| 82011E | BATHROOM SCALES, FAG BREAK | bath_beauty（洗浴美容用品） | other（其他） | 有人不确定 | A=D |  |
| 84946 | ANTIQUE SILVER TEA GLASS ETCHED | candle_holder_lantern（烛台和灯笼） | mugs_cups（杯子和马克杯） | 都确定 | A=D | unparseable;retried |
| 85089 | CANDY SPOT BUNNY | tabletop_decorations（桌面装饰） | egg_cups（蛋杯和蛋套） | 有人不确定 | C=A |  |

R1 最常见的错误方向（金标准 → R1）：decorative_candles → party_bags_supplies ×2；soft_toys → sewing_craft ×2；tabletop_decorations → hanging_ornaments ×2；candle_holder_lantern → mugs_cups ×1；candle_holder_lantern → trinket_jewellery_box ×1；bunting_garland → hanging_ornaments ×1；bath_beauty → other ×1；gift_boxes → clothing_slippers ×1
