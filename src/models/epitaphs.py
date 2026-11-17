"""What is carved on the churchyard's gravestones, read with "Read" in a gravestone's menu.

A gravestone is a decoration on the map whose Tiled object has an `Epitaph`
property naming one of EPITAPHS by its key (`House.epitaph`). There are more
here than stones on the map, so a new stone only needs the property.

The dead are the town's own from before the game begins (the calendar starts
in 1500, `CALENDAR_START_YEAR`), their years carved in Roman numerals as was
done. True to the time (the Wars of the Roses, the sweating sickness of 1485,
the wool and salt trade, guilds and aldermen, Lent), only louder about it than
a mason would have been. No pygame here; the stone is drawn in
src/ui/helper_modules/gravestone_window.py.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Epitaph:
    key: str                  # what a gravestone's `Epitaph` property names
    name: str                 # the first line, carved largest
    born: Optional[int]       # None when the stone does not say
    died: int
    lines: Tuple[str, ...]    # the inscription, each a line of its own (wrapped if too long)


EPITAPHS: Tuple[Epitaph, ...] = (
    Epitaph('wool_merchant', 'Godric Fuller', 1431, 1487, (
        'Merchant of the Staple, dealer in wool.',
        'He bought at four and sold at nine.',
        'The Lord has taken the difference.',
    )),
    Epitaph('knight', 'Sir Hugh de Mardale', 1440, 1485, (
        'Knight, who rode out to the King\'s war',
        'and came home in a cart.',
        'Which king, he never quite said.',
        'Orate pro anima eius.',
    )),
    Epitaph('alderman', 'Roger Wainwright', 1438, 1494, (
        'Alderman of this town,',
        'thrice chosen to the council, once honestly.',
        'He gave a banquet every season',
        'and a grudge to every man who beat him.',
        'Requiescat in pace.',
    )),
    Epitaph('sweat', 'The House of Fletcher', None, 1485, (
        'Here lie seven of one house,',
        'taken by the Sweating Sickness',
        'in a single week of summer.',
        'Hale at dinner, dead by supper.',
        'Memento mori.',
    )),
    Epitaph('woodcutter', 'Thomas Wode', 1445, 1490, (
        'Woodcutter, father of Osric.',
        'He felled a thousand oaks.',
        'The last of them fell back.',
    )),
    Epitaph('alewife', 'Agnes Brewster', 1452, 1489, (
        'Alewife at the Golden Sheaf.',
        'Her ale was strong and her measures full;',
        'few in this town can say the same.',
    )),
    Epitaph('herb_wife', 'Old Margery', 1416, 1499, (
        'Herb-wife and midwife,',
        'aged fourscore and three.',
        'She cured the whole town of everything',
        'but herself, and buried every physician',
        'who called her a witch.',
    )),
    Epitaph('guild_clerk', 'Hamo Ledger', 1451, 1497, (
        'Clerk to the merchants\' guild.',
        'His books balanced to the farthing',
        'for six and twenty years.',
        'May his sins be audited as kindly.',
    )),
    Epitaph('widow', 'Eleanor Thorne', 1447, 1499, (
        'Widow of three husbands,',
        'who kept all three of their shops.',
        'Pray for the husbands.',
        'She needs no prayers.',
    )),
    Epitaph('salter', 'Bartholomew the Salter', 1449, 1491, (
        'Dealer in salt from the bay.',
        'He was worth his salt,',
        'and every grain of it was taxed.',
    )),
    Epitaph('fleming', 'Master Jehan of Bruges', 1442, 1488, (
        'Cloth merchant of Flanders.',
        'He came for a season and stayed for eternity.',
        'His creditors went home without him.',
    )),
    Epitaph('moneylender', 'Gilbert Penny', 1433, 1493, (
        'Who lent to his neighbours',
        'at no interest whatsoever,',
        'as he swore upon his deathbed',
        'before three priests and a notary.',
    )),
    Epitaph('fisherman', 'Tobias Pyke', 1460, 1492, (
        'Fisherman of the Wide River.',
        'He swore the one that got away was this long.',
        'Here he lies, three ells of him,',
        'and the fish still swims.',
    )),
    Epitaph('sacristan', 'Brother Anselm', 1428, 1490, (
        'Sacristan of this church.',
        'He rang the bell at every hour',
        'for forty years, the night ones too.',
        'Let him sleep now. Let us all sleep.',
    )),
    Epitaph('glutton', 'Walter Gorge', 1458, 1496, (
        'Who ate an eel pie on Good Friday,',
        'a goose at Easter and a whole swan',
        'at the guild\'s feast of Michaelmas.',
        'Gone, we trust, to a better table.',
    )),
)

BY_KEY: Dict[str, Epitaph] = {e.key: e for e in EPITAPHS}

_ROMAN = ((1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'),
          (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I'))


def roman(number: int) -> str:
    """A year as the masons carved it, in the late medieval way: four Cs for 400 (MCCCCLXXXV)."""
    out = []
    for value, letters in _ROMAN:
        while number >= value:
            out.append(letters)
            number -= value
    return ''.join(out).replace('CD', 'CCCC')


def years_line(epitaph: Epitaph) -> str:
    """The years under the name: both if the stone says when they were born, else when they died."""
    if epitaph.born is None:
        return f'Anno Domini {roman(epitaph.died)}'
    return f'{roman(epitaph.born)} – {roman(epitaph.died)}'


def epitaph(key: str) -> Optional[Epitaph]:
    """The epitaph a gravestone's `Epitaph` property names, or None for an unknown key."""
    return BY_KEY.get((key or '').strip())
