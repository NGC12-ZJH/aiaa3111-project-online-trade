# 现有规则 taxonomy 分析

仅标注原有 Discovery 规则；未重新挖掘、未改变筛选或排序，未使用 Validation/Test。
范围包括 G、C0/C1/C2，以及 20 个随机种子各三个组（64 个范围）。统计对象为 generated_here 且 eligible 的方向规则，A→B 与 B→A 分别计数。

三商品规则按前后件的全部商品统一判定：全部同一 l2 为同类换款；否则全部属于同一个非 none design_line 为同系列配套；其余为真正跨类搭配。三商品中只有部分商品共享系列仍归第三类。含 other 单列为未分类，不强行解释为跨类。该分类描述标签关系，不证明款式替代、功能互补或业务价值。

占比以该范围、该长度的全部合格方向规则为分母。跨类榜包括同系列配套和真正跨类搭配；先筛选跨类，再按 joint_count↓、confidence↓、lift↓、rule_id↑ 排序。各范围独立 Top50，前10/20即对应榜单，不是系统预算。0表示二/三商品混合榜；不足50不补齐。


## G/L 分类数量与占比

| method | seed | group_id | length | rule_type | count | total | share |
|---|---|---|---|---|---|---|---|
| G |  | GLOBAL | 2 | 同类换款 | 509 | 720 | 70.69% |
| G |  | GLOBAL | 2 | 同系列配套 | 21 | 720 | 2.92% |
| G |  | GLOBAL | 2 | 真正跨类搭配 | 190 | 720 | 26.39% |
| G |  | GLOBAL | 2 | 未分类（含other） | 0 | 720 | 0.00% |
| G |  | GLOBAL | 3 | 同类换款 | 276 | 396 | 69.70% |
| G |  | GLOBAL | 3 | 同系列配套 | 3 | 396 | 0.76% |
| G |  | GLOBAL | 3 | 真正跨类搭配 | 117 | 396 | 29.55% |
| G |  | GLOBAL | 3 | 未分类（含other） | 0 | 396 | 0.00% |
| L |  | 0 | 2 | 同类换款 | 38 | 43 | 88.37% |
| L |  | 0 | 2 | 同系列配套 | 0 | 43 | 0.00% |
| L |  | 0 | 2 | 真正跨类搭配 | 5 | 43 | 11.63% |
| L |  | 0 | 2 | 未分类（含other） | 0 | 43 | 0.00% |
| L |  | 0 | 3 | 同类换款 | 3 | 3 | 100.00% |
| L |  | 0 | 3 | 同系列配套 | 0 | 3 | 0.00% |
| L |  | 0 | 3 | 真正跨类搭配 | 0 | 3 | 0.00% |
| L |  | 0 | 3 | 未分类（含other） | 0 | 3 | 0.00% |
| L |  | 1 | 2 | 同类换款 | 434 | 633 | 68.56% |
| L |  | 1 | 2 | 同系列配套 | 22 | 633 | 3.48% |
| L |  | 1 | 2 | 真正跨类搭配 | 177 | 633 | 27.96% |
| L |  | 1 | 2 | 未分类（含other） | 0 | 633 | 0.00% |
| L |  | 1 | 3 | 同类换款 | 177 | 210 | 84.29% |
| L |  | 1 | 3 | 同系列配套 | 0 | 210 | 0.00% |
| L |  | 1 | 3 | 真正跨类搭配 | 33 | 210 | 15.71% |
| L |  | 1 | 3 | 未分类（含other） | 0 | 210 | 0.00% |
| L |  | 2 | 2 | 同类换款 | 560 | 900 | 62.22% |
| L |  | 2 | 2 | 同系列配套 | 43 | 900 | 4.78% |
| L |  | 2 | 2 | 真正跨类搭配 | 297 | 900 | 33.00% |
| L |  | 2 | 2 | 未分类（含other） | 0 | 900 | 0.00% |
| L |  | 2 | 3 | 同类换款 | 387 | 690 | 56.09% |
| L |  | 2 | 3 | 同系列配套 | 3 | 690 | 0.43% |
| L |  | 2 | 3 | 真正跨类搭配 | 300 | 690 | 43.48% |
| L |  | 2 | 3 | 未分类（含other） | 0 | 690 | 0.00% |

## G/GLOBAL 2商品跨类 Top10

| rank | 规则 | 子类 | rule_type | joint_count | support | confidence | lift |
|---|---|---|---|---|---|---|---|
| 1 | JUMBO STORAGE BAG SUKI → JUMBO BAG RED WHITE SPOTTY | 家居洗衣收纳 → 大号购物袋 | 真正跨类搭配 | 229 | 3.04% | 53.76% | 5.3 |
| 2 | JUMBO BAG RED WHITE SPOTTY → JUMBO STORAGE BAG SUKI | 大号购物袋 → 家居洗衣收纳 | 真正跨类搭配 | 229 | 3.04% | 30.01% | 5.3 |
| 3 | HEART OF WICKER LARGE → WHITE HANGING HEART T-LIGHT HOLDER | 悬挂装饰（含圣诞树挂饰） → 烛台和灯笼 | 真正跨类搭配 | 218 | 2.90% | 41.60% | 2.72 |
| 4 | LUNCH BAG RED SPOTTY → JUMBO BAG RED WHITE SPOTTY | 午餐包 → 大号购物袋 | 同系列配套 | 208 | 2.77% | 35.31% | 3.48 |
| 5 | JUMBO BAG RED WHITE SPOTTY → LUNCH BAG RED SPOTTY | 大号购物袋 → 午餐包 | 同系列配套 | 208 | 2.77% | 27.26% | 3.48 |
| 6 | HEART OF WICKER SMALL → WHITE HANGING HEART T-LIGHT HOLDER | 悬挂装饰（含圣诞树挂饰） → 烛台和灯笼 | 真正跨类搭配 | 178 | 2.37% | 39.47% | 2.58 |
| 7 | JUMBO STORAGE BAG SUKI → JUMBO BAG PINK WITH WHITE SPOTS | 家居洗衣收纳 → 大号购物袋 | 真正跨类搭配 | 166 | 2.21% | 38.97% | 6.59 |
| 8 | JUMBO BAG PINK WITH WHITE SPOTS → JUMBO STORAGE BAG SUKI | 大号购物袋 → 家居洗衣收纳 | 真正跨类搭配 | 166 | 2.21% | 37.30% | 6.59 |
| 9 | JUMBO STORAGE BAG SUKI → JUMBO SHOPPER VINTAGE RED PAISLEY | 家居洗衣收纳 → 大号购物袋 | 真正跨类搭配 | 164 | 2.18% | 38.50% | 6.61 |
| 10 | JUMBO SHOPPER VINTAGE RED PAISLEY → JUMBO STORAGE BAG SUKI | 大号购物袋 → 家居洗衣收纳 | 真正跨类搭配 | 164 | 2.18% | 37.44% | 6.61 |

## G/GLOBAL 3商品跨类 Top10

| rank | 规则 | 子类 | rule_type | joint_count | support | confidence | lift |
|---|---|---|---|---|---|---|---|
| 1 | JUMBO STORAGE BAG SUKI + JUMBO BAG PINK WITH WHITE SPOTS → JUMBO BAG RED WHITE SPOTTY | 家居洗衣收纳 + 大号购物袋 → 大号购物袋 | 真正跨类搭配 | 116 | 1.54% | 69.88% | 6.89 |
| 2 | JUMBO STORAGE BAG SUKI + JUMBO BAG RED WHITE SPOTTY → JUMBO BAG PINK WITH WHITE SPOTS | 家居洗衣收纳 + 大号购物袋 → 大号购物袋 | 真正跨类搭配 | 116 | 1.54% | 50.66% | 8.56 |
| 3 | JUMBO BAG PINK WITH WHITE SPOTS + JUMBO BAG RED WHITE SPOTTY → JUMBO STORAGE BAG SUKI | 大号购物袋 + 大号购物袋 → 家居洗衣收纳 | 真正跨类搭配 | 116 | 1.54% | 43.28% | 7.64 |
| 4 | JUMBO STORAGE BAG SUKI + JUMBO BAG STRAWBERRY → JUMBO BAG RED WHITE SPOTTY | 家居洗衣收纳 + 大号购物袋 → 大号购物袋 | 真正跨类搭配 | 114 | 1.52% | 69.94% | 6.89 |
| 5 | JUMBO STORAGE BAG SUKI + JUMBO BAG RED WHITE SPOTTY → JUMBO BAG STRAWBERRY | 家居洗衣收纳 + 大号购物袋 → 大号购物袋 | 真正跨类搭配 | 114 | 1.52% | 49.78% | 9.22 |
| 6 | JUMBO BAG RED WHITE SPOTTY + JUMBO BAG STRAWBERRY → JUMBO STORAGE BAG SUKI | 大号购物袋 + 大号购物袋 → 家居洗衣收纳 | 真正跨类搭配 | 114 | 1.52% | 47.11% | 8.32 |
| 7 | WOODEN PICTURE FRAME WHITE FINISH + WHITE HANGING HEART T-LIGHT HOLDER → WOODEN FRAME ANTIQUE WHITE | 相框和相册 + 烛台和灯笼 → 相框和相册 | 真正跨类搭配 | 112 | 1.49% | 70.44% | 13.05 |
| 8 | WOODEN FRAME ANTIQUE WHITE + WHITE HANGING HEART T-LIGHT HOLDER → WOODEN PICTURE FRAME WHITE FINISH | 相框和相册 + 烛台和灯笼 → 相框和相册 | 真正跨类搭配 | 112 | 1.49% | 69.14% | 13.76 |
| 9 | WOODEN PICTURE FRAME WHITE FINISH + WOODEN FRAME ANTIQUE WHITE → WHITE HANGING HEART T-LIGHT HOLDER | 相框和相册 + 相框和相册 → 烛台和灯笼 | 真正跨类搭配 | 112 | 1.49% | 43.24% | 2.83 |
| 10 | HEART OF WICKER SMALL + WHITE HANGING HEART T-LIGHT HOLDER → HEART OF WICKER LARGE | 悬挂装饰（含圣诞树挂饰） + 烛台和灯笼 → 悬挂装饰（含圣诞树挂饰） | 真正跨类搭配 | 110 | 1.46% | 61.80% | 8.87 |

## L/0 2商品跨类 Top10

| rank | 规则 | 子类 | rule_type | joint_count | support | confidence | lift |
|---|---|---|---|---|---|---|---|
| 1 | CHILDS BREAKFAST SET DOLLY GIRL → CHILDS BREAKFAST SET SPACEBOY | 游戏套装和玩偶 → 餐桌配件与套装 | 真正跨类搭配 | 20 | 2.50% | 71.43% | 16.35 |
| 2 | CHILDS BREAKFAST SET SPACEBOY → CHILDS BREAKFAST SET DOLLY GIRL | 餐桌配件与套装 → 游戏套装和玩偶 | 真正跨类搭配 | 20 | 2.50% | 57.14% | 16.35 |
| 3 | PACK OF 6 PANNETONE GIFT BOXES → PACK OF 6 BIRDY GIFT TAGS | 礼品盒 → 礼品包装纸和标签 | 真正跨类搭配 | 20 | 2.50% | 54.05% | 8.66 |
| 4 | PACK OF 6 BIRDY GIFT TAGS → PACK OF 6 PANNETONE GIFT BOXES | 礼品包装纸和标签 → 礼品盒 | 真正跨类搭配 | 20 | 2.50% | 40.00% | 8.66 |
| 5 | HEART OF WICKER LARGE → WHITE HANGING HEART T-LIGHT HOLDER | 悬挂装饰（含圣诞树挂饰） → 烛台和灯笼 | 真正跨类搭配 | 20 | 2.50% | 32.26% | 2.35 |

## L/1 2商品跨类 Top10

| rank | 规则 | 子类 | rule_type | joint_count | support | confidence | lift |
|---|---|---|---|---|---|---|---|
| 1 | HEART OF WICKER LARGE → WHITE HANGING HEART T-LIGHT HOLDER | 悬挂装饰（含圣诞树挂饰） → 烛台和灯笼 | 真正跨类搭配 | 88 | 4.05% | 46.56% | 2.98 |
| 2 | WHITE HANGING HEART T-LIGHT HOLDER → HEART OF WICKER LARGE | 烛台和灯笼 → 悬挂装饰（含圣诞树挂饰） | 真正跨类搭配 | 88 | 4.05% | 25.88% | 2.98 |
| 3 | HEART OF WICKER SMALL → WHITE HANGING HEART T-LIGHT HOLDER | 悬挂装饰（含圣诞树挂饰） → 烛台和灯笼 | 真正跨类搭配 | 55 | 2.53% | 39.01% | 2.49 |
| 4 | ASSORTED COLOUR BIRD ORNAMENT → WHITE HANGING HEART T-LIGHT HOLDER | 悬挂装饰（含圣诞树挂饰） → 烛台和灯笼 | 真正跨类搭配 | 48 | 2.21% | 31.17% | 1.99 |
| 5 | LUNCH BAG RED SPOTTY → JUMBO BAG RED WHITE SPOTTY | 午餐包 → 大号购物袋 | 同系列配套 | 47 | 2.16% | 31.13% | 3.72 |
| 6 | JUMBO BAG RED WHITE SPOTTY → LUNCH BAG RED SPOTTY | 大号购物袋 → 午餐包 | 同系列配套 | 47 | 2.16% | 25.82% | 3.72 |
| 7 | PAINTED METAL PEARS ASSORTED → ASSORTED COLOUR BIRD ORNAMENT | 桌面装饰 → 悬挂装饰（含圣诞树挂饰） | 真正跨类搭配 | 46 | 2.12% | 93.88% | 13.25 |
| 8 | ASSORTED COLOUR BIRD ORNAMENT → PAINTED METAL PEARS ASSORTED | 悬挂装饰（含圣诞树挂饰） → 桌面装饰 | 真正跨类搭配 | 46 | 2.12% | 29.87% | 13.25 |
| 9 | 60 CAKE CASES VINTAGE CHRISTMAS → PAPER CHAIN KIT VINTAGE CHRISTMAS | 蛋糕纸托 → 彩旗和花环 | 真正跨类搭配 | 42 | 1.93% | 44.68% | 9.25 |
| 10 | PAPER CHAIN KIT VINTAGE CHRISTMAS → 60 CAKE CASES VINTAGE CHRISTMAS | 彩旗和花环 → 蛋糕纸托 | 真正跨类搭配 | 42 | 1.93% | 40.00% | 9.25 |

## L/1 3商品跨类 Top10

| rank | 规则 | 子类 | rule_type | joint_count | support | confidence | lift |
|---|---|---|---|---|---|---|---|
| 1 | HEART OF WICKER SMALL + WHITE HANGING HEART T-LIGHT HOLDER → HEART OF WICKER LARGE | 悬挂装饰（含圣诞树挂饰） + 烛台和灯笼 → 悬挂装饰（含圣诞树挂饰） | 真正跨类搭配 | 40 | 1.84% | 72.73% | 8.36 |
| 2 | HEART OF WICKER LARGE + WHITE HANGING HEART T-LIGHT HOLDER → HEART OF WICKER SMALL | 悬挂装饰（含圣诞树挂饰） + 烛台和灯笼 → 悬挂装饰（含圣诞树挂饰） | 真正跨类搭配 | 40 | 1.84% | 45.45% | 7.01 |
| 3 | HEART OF WICKER SMALL + HEART OF WICKER LARGE → WHITE HANGING HEART T-LIGHT HOLDER | 悬挂装饰（含圣诞树挂饰） + 悬挂装饰（含圣诞树挂饰） → 烛台和灯笼 | 真正跨类搭配 | 40 | 1.84% | 43.96% | 2.81 |
| 4 | FELTCRAFT BUTTERFLY HEARTS + FELTCRAFT CUSHION RABBIT → FELTCRAFT CUSHION BUTTERFLY | 缝纫和手工艺套装 + 靠垫与靠垫套 → 靠垫与靠垫套 | 真正跨类搭配 | 26 | 1.20% | 96.30% | 25.21 |
| 5 | FELTCRAFT BUTTERFLY HEARTS + FELTCRAFT CUSHION BUTTERFLY → FELTCRAFT CUSHION RABBIT | 缝纫和手工艺套装 + 靠垫与靠垫套 → 靠垫与靠垫套 | 真正跨类搭配 | 26 | 1.20% | 89.66% | 24.98 |
| 6 | FELTCRAFT 6 FLOWER FRIENDS + FELTCRAFT CUSHION RABBIT → FELTCRAFT CUSHION BUTTERFLY | 缝纫和手工艺套装 + 靠垫与靠垫套 → 靠垫与靠垫套 | 真正跨类搭配 | 26 | 1.20% | 89.66% | 23.47 |
| 7 | RED HANGING HEART T-LIGHT HOLDER + HEART OF WICKER LARGE → WHITE HANGING HEART T-LIGHT HOLDER | 烛台和灯笼 + 悬挂装饰（含圣诞树挂饰） → 烛台和灯笼 | 真正跨类搭配 | 26 | 1.20% | 81.25% | 5.19 |
| 8 | FELTCRAFT 6 FLOWER FRIENDS + FELTCRAFT CUSHION BUTTERFLY → FELTCRAFT CUSHION RABBIT | 缝纫和手工艺套装 + 靠垫与靠垫套 → 靠垫与靠垫套 | 真正跨类搭配 | 26 | 1.20% | 78.79% | 21.95 |
| 9 | FELTCRAFT BUTTERFLY HEARTS + 3 STRIPEY MICE FELTCRAFT → FELTCRAFT 6 FLOWER FRIENDS | 缝纫和手工艺套装 + 毛绒玩具 → 缝纫和手工艺套装 | 真正跨类搭配 | 26 | 1.20% | 74.29% | 14.04 |
| 10 | FELTCRAFT 6 FLOWER FRIENDS + 3 STRIPEY MICE FELTCRAFT → FELTCRAFT BUTTERFLY HEARTS | 缝纫和手工艺套装 + 毛绒玩具 → 缝纫和手工艺套装 | 真正跨类搭配 | 26 | 1.20% | 66.67% | 16.1 |

## L/2 2商品跨类 Top10

| rank | 规则 | 子类 | rule_type | joint_count | support | confidence | lift |
|---|---|---|---|---|---|---|---|
| 1 | JUMBO STORAGE BAG SUKI → JUMBO BAG RED WHITE SPOTTY | 家居洗衣收纳 → 大号购物袋 | 真正跨类搭配 | 175 | 3.85% | 56.09% | 4.86 |
| 2 | JUMBO BAG RED WHITE SPOTTY → JUMBO STORAGE BAG SUKI | 大号购物袋 → 家居洗衣收纳 | 真正跨类搭配 | 175 | 3.85% | 33.33% | 4.86 |
| 3 | LUNCH BAG RED SPOTTY → JUMBO BAG RED WHITE SPOTTY | 午餐包 → 大号购物袋 | 同系列配套 | 144 | 3.17% | 37.11% | 3.21 |
| 4 | JUMBO BAG RED WHITE SPOTTY → LUNCH BAG RED SPOTTY | 大号购物袋 → 午餐包 | 同系列配套 | 144 | 3.17% | 27.43% | 3.21 |
| 5 | JUMBO STORAGE BAG SUKI → JUMBO BAG PINK WITH WHITE SPOTS | 家居洗衣收纳 → 大号购物袋 | 真正跨类搭配 | 137 | 3.01% | 43.91% | 6.16 |
| 6 | JUMBO BAG PINK WITH WHITE SPOTS → JUMBO STORAGE BAG SUKI | 大号购物袋 → 家居洗衣收纳 | 真正跨类搭配 | 137 | 3.01% | 42.28% | 6.16 |
| 7 | JUMBO SHOPPER VINTAGE RED PAISLEY → JUMBO STORAGE BAG SUKI | 大号购物袋 → 家居洗衣收纳 | 真正跨类搭配 | 129 | 2.84% | 42.86% | 6.25 |
| 8 | JUMBO STORAGE BAG SUKI → JUMBO SHOPPER VINTAGE RED PAISLEY | 家居洗衣收纳 → 大号购物袋 | 真正跨类搭配 | 129 | 2.84% | 41.35% | 6.25 |
| 9 | JUMBO BAG STRAWBERRY → JUMBO STORAGE BAG SUKI | 大号购物袋 → 家居洗衣收纳 | 真正跨类搭配 | 124 | 2.73% | 43.51% | 6.34 |
| 10 | JUMBO STORAGE BAG SUKI → JUMBO BAG STRAWBERRY | 家居洗衣收纳 → 大号购物袋 | 真正跨类搭配 | 124 | 2.73% | 39.74% | 6.34 |

## L/2 3商品跨类 Top10

| rank | 规则 | 子类 | rule_type | joint_count | support | confidence | lift |
|---|---|---|---|---|---|---|---|
| 1 | JUMBO STORAGE BAG SUKI + JUMBO BAG PINK WITH WHITE SPOTS → JUMBO BAG RED WHITE SPOTTY | 家居洗衣收纳 + 大号购物袋 → 大号购物袋 | 真正跨类搭配 | 94 | 2.07% | 68.61% | 5.94 |
| 2 | JUMBO STORAGE BAG SUKI + JUMBO BAG RED WHITE SPOTTY → JUMBO BAG PINK WITH WHITE SPOTS | 家居洗衣收纳 + 大号购物袋 → 大号购物袋 | 真正跨类搭配 | 94 | 2.07% | 53.71% | 7.54 |
| 3 | JUMBO BAG PINK WITH WHITE SPOTS + JUMBO BAG RED WHITE SPOTTY → JUMBO STORAGE BAG SUKI | 大号购物袋 + 大号购物袋 → 家居洗衣收纳 | 真正跨类搭配 | 94 | 2.07% | 47.24% | 6.88 |
| 4 | WOODEN PICTURE FRAME WHITE FINISH + WHITE HANGING HEART T-LIGHT HOLDER → WOODEN FRAME ANTIQUE WHITE | 相框和相册 + 烛台和灯笼 → 相框和相册 | 真正跨类搭配 | 87 | 1.91% | 76.32% | 11.72 |
| 5 | WOODEN FRAME ANTIQUE WHITE + WHITE HANGING HEART T-LIGHT HOLDER → WOODEN PICTURE FRAME WHITE FINISH | 相框和相册 + 烛台和灯笼 → 相框和相册 | 真正跨类搭配 | 87 | 1.91% | 73.11% | 12.04 |
| 6 | WOODEN PICTURE FRAME WHITE FINISH + WOODEN FRAME ANTIQUE WHITE → WHITE HANGING HEART T-LIGHT HOLDER | 相框和相册 + 相框和相册 → 烛台和灯笼 | 真正跨类搭配 | 87 | 1.91% | 43.94% | 2.86 |
| 7 | JUMBO STORAGE BAG SUKI + JUMBO BAG STRAWBERRY → JUMBO BAG RED WHITE SPOTTY | 家居洗衣收纳 + 大号购物袋 → 大号购物袋 | 真正跨类搭配 | 85 | 1.87% | 68.55% | 5.94 |
| 8 | JUMBO BAG RED WHITE SPOTTY + JUMBO BAG STRAWBERRY → JUMBO STORAGE BAG SUKI | 大号购物袋 + 大号购物袋 → 家居洗衣收纳 | 真正跨类搭配 | 85 | 1.87% | 51.83% | 7.55 |
| 9 | JUMBO STORAGE BAG SUKI + JUMBO BAG RED WHITE SPOTTY → JUMBO BAG STRAWBERRY | 家居洗衣收纳 + 大号购物袋 → 大号购物袋 | 真正跨类搭配 | 85 | 1.87% | 48.57% | 7.75 |
| 10 | WOOD 2 DRAWER CABINET WHITE FINISH + WOODEN FRAME ANTIQUE WHITE → WOODEN PICTURE FRAME WHITE FINISH | 家具与抽屉把手 + 相框和相册 → 相框和相册 | 真正跨类搭配 | 83 | 1.83% | 87.37% | 14.39 |

## 完整输出
classification_counts.csv：所有64范围的分类占比（含零计数）；cross_category_top50.csv：混合、二商品、三商品完整Top50；candidate_taxonomy.csv：共同候选池标签；rule_evidence_taxonomy.csv.gz：全部证据附标签。随机组保持每个seed分开，不当成独立的60次重复。