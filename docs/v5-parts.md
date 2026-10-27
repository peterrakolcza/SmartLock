# v5 part list (AliExpress)

Everything for one lock, apart from the printed parts and the PCB. Prices are from AliExpress Hungary (HUF) on 2026-10-27, where a listing was checked. The others link to a search with the exact terms to use. Most of these come in packs, so one order covers a spare.

**Order the PCB assembled, not from AliExpress.** `PCB/v5/fab` already has what JLCPCB (or PCBWay) needs for assembly: the Gerbers, `bom.csv` (manufacturer part numbers) and `pick_and_place.csv`. The board has 0402 parts, a TSSOP-16 and a module with a centre pad, which is not a hand-soldering job. The chips are listed at the end in case you want to hand-assemble anyway.

## Drive

| # | Part | Qty | What to pick | Where | Price |
| :-: | :-- | :-: | :-- | :-- | --: |
| 1 | N20 gearmotor, metal gearbox | 1 (+1 spare) | **6 V, 600 RPM** (= 50:1 on the common 30 000 rpm motor), 3 mm D-shaft, 10 mm shaft | [listing, 10 000+ sold](https://www.aliexpress.com/item/1005010285600111.html) | HUF 1 547 |
| 2 | Worm + worm wheel, brass, module 0.5 | 1 set | see [the note below](#worm-gear-set) | [0.5 modulus worm gear kits](https://www.aliexpress.com/w/wholesale-0.5-modulus-worm-gear-kit-brass.html), [worm with 2.98 mm bore](https://www.aliexpress.com/item/1005009888773776.html) | HUF 436 (worm), set ~HUF 2 200-3 000 |
| 3 | Steel shaft Ø 3 mm | 1 | hub axle, cut to **22 mm** | [search: 3mm steel rod shaft 50mm](https://www.aliexpress.com/w/wholesale-3mm-steel-rod-shaft-50mm.html) | |
| 4 | Steel dowel pins Ø 2 × 8 mm | 2 | worm wheel → hub (drill two Ø 2.2 holes through the wheel web at r = 6 mm) | [search: dowel pin 2x8 stainless](https://www.aliexpress.com/w/wholesale-dowel-pin-2x8-stainless.html) | |
| 5 | Steel dowel pin Ø 3 × 5 mm | 1 | spiral follower pin | [search: dowel pin 3x5 stainless](https://www.aliexpress.com/w/wholesale-dowel-pin-3x5-stainless.html) | |

## Sensing, power, wiring

| # | Part | Qty | What to pick | Where |
| :-: | :-- | :-: | :-- | :-- |
| 6 | Neodymium disc magnet N52, **5 × 2 mm**, axially magnetised | 1 (pack of 10+) | thumb-turn magnet | [search: N52 magnet 5x2mm](https://www.aliexpress.com/w/wholesale-n52-magnet-5x2mm.html) |
| 7 | Neodymium disc magnet N52, **3 × 2 mm**, axially magnetised | 1 (pack) | hub magnet | [search: N52 magnet 3x2mm](https://www.aliexpress.com/w/wholesale-n52-magnet-3x2mm.html) |
| 8 | Li-ion pouch **603450, 3.7 V, 1200 mAh, with protection board** | 1 | max 50 × 34 × 6 mm; it usually comes with a JST PH 2.0 plug, so cut it off and fit #9 | [search: 603450 1200mAh lipo](https://www.aliexpress.com/w/wholesale-603450-1200mah-lipo-battery.html) |
| 9 | JST **SH 1.0 mm**, 2-pin, pre-crimped cable with plug | 2 | battery and motor leads (the board has SM02B-SRSS-TB sockets) | [search: JST SH 1.0 2 pin cable](https://www.aliexpress.com/w/wholesale-jst-sh-1.0-2pin-cable.html) |

## Fasteners and mounting

| # | Part | Qty | Where it goes | Where |
| :-: | :-- | :-: | :-- | :-- |
| 10 | M3 heat-set insert, **M3 × 3 × 4.2 mm** (brass, knurled) | 2 | adapter cage walls, pressed in with a soldering iron | [search: M3x3x4.2 heat set insert](https://www.aliexpress.com/w/wholesale-m3x3x4.2-heat-set-insert.html) |
| 11 | M3 × 16 socket head screw | 2 | jaw screws (tips push the jaws onto the thumb-turn). **No longer than 16 mm**: longer heads hit the case when the adapter turns | [search: M3x16 socket head screw](https://www.aliexpress.com/w/wholesale-m3x16-socket-head-screw.html) |
| 12 | M3 × 8 button head screw | 1 | case → base lock screw (self-taps into the base) | [search: M3x8 button head screw](https://www.aliexpress.com/w/wholesale-m3x8-button-head-screw.html) |
| 13 | M2 × 5 self-tapping pan head screw | 3 | deck → case | [search: M2x5 self tapping screw](https://www.aliexpress.com/w/wholesale-m2x5-self-tapping-screw.html) |
| 14 | 3M VHB tape, **5952** (or 4910), 1.1 mm | ~25 cm² | under the base. Cut it to the base ring | [search: 3M VHB 5952](https://www.aliexpress.com/w/wholesale-3m-vhb-5952.html) |

> **About the VHB tape:** fake "3M VHB" is common. Buy from 3M's official store or a local hardware or car-parts shop. The tape is the only thing holding the lock on the door.

## Printing

PETG for all parts (about 60 g per lock), plus a few grams of **clear** PETG for the light pipe. The STLs are in `3D printed case/v5/stl`, already in print orientation.

## Worm gear set

The CAD was designed around a module 0.6 worm set, but on AliExpress module 0.6 only comes as spur pinions. Worm sets are module 0.5. Before ordering #2, the CAD has to move to module 0.5 so the worm-to-wheel centre distance and the tooth strength check match the real part. Smaller teeth are weaker, so the wheel's face width decides between a 30T wheel (faster) and a 40T wheel (more tooth margin, 33 % slower). **Don't order #2 until that's settled.**

## PCB chips (only for hand assembly)

The part numbers match `PCB/v5/fab/bom.csv`. The passives are 0402 and 0603 (values in the BOM), and a 0402 resistor and capacitor sample book covers them.

| Part | Package | Search |
| :-- | :-- | :-- |
| ESP32-C6-MINI-1-**N4** (4 MB) | module | [search](https://www.aliexpress.com/w/wholesale-esp32-c6-mini-1-n4.html) |
| DRV8833PWR | TSSOP-16 | [search](https://www.aliexpress.com/w/wholesale-drv8833pwr.html) |
| MCP73831T-2ACI/OT | SOT-23-5 | [search](https://www.aliexpress.com/w/wholesale-mcp73831t-2aci-ot.html) |
| RT9080-33GJ5 | SOT-23-5 | [search](https://www.aliexpress.com/w/wholesale-rt9080-33gj5.html) |
| DRV5032FBDBZR (×2) | SOT-23 | [search](https://www.aliexpress.com/w/wholesale-drv5032fbdbzr.html) |
| USB-C 16-pin SMD receptacle (GCT USB4105 footprint) | | [search](https://www.aliexpress.com/w/wholesale-usb4105-gf-a.html) |
| JST SM02B-SRSS-TB (×2) | SMD, horizontal | [search](https://www.aliexpress.com/w/wholesale-sm02b-srss-tb.html) |
| Panasonic EVQ-P7A01P side-push switch | SMD | [search](https://www.aliexpress.com/w/wholesale-evqp7a01p.html) |
| 0.15 Ω 0805 current-sense resistor (1 %) | 0805 | [search](https://www.aliexpress.com/w/wholesale-0805-0.15r-resistor-1%25.html) |
