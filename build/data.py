# -*- coding: utf-8 -*-
"""Única fuente de datos del catálogo de Grano Claro 1.1.
GC-001…GC-006 conservan precio, peso y existencias de la versión 1.0.
Variedades y regiones de Costa Rica: verificadas (ver SOURCES). Altitudes y notas de cata: ficticias."""
import unicodedata

DATE_ISO = '2026-10-15'
DATE_ES = '15 de octubre de 2026'
VERSION = '1.1'

P = [
    dict(sku='GC-001', short='Huila', country='Colombia', origin='CO', region='Huila',
         varieties=['Caturra', 'Castillo'], alt=None, process='Lavado', roast='medium',
         weight=340, price='14.50', stock=12, notes='Panela, mandarina y cacao.'),
    dict(sku='GC-002', short='Yirgacheffe', country='Etiopía', origin='ET', region='Yirgacheffe',
         varieties=['Variedades locales'], alt=None, process='Lavado', roast='light',
         weight=340, price='17.00', stock=8, notes='Bergamota, jazmín y limón.'),
    dict(sku='GC-003', short='Huehuetenango', country='Guatemala', origin='GT', region='Huehuetenango',
         varieties=['Bourbon', 'Caturra'], alt=None, process='Lavado', roast='dark',
         weight=340, price='13.00', stock=0, notes='Chocolate amargo y nuez.'),
    dict(sku='GC-004', short='Nyeri', country='Kenia', origin='KE', region='Nyeri',
         varieties=['SL28', 'SL34'], alt=None, process='Lavado', roast='light',
         weight=250, price='18.50', stock=5, notes='Grosella negra y pomelo.'),
    dict(sku='GC-005', short='Cerrado Mineiro', country='Brasil', origin='BR', region='Cerrado Mineiro',
         varieties=['Mundo Novo', 'Catuaí'], alt=None, process='Natural', roast='medium',
         weight=500, price='15.00', stock=20, notes='Maní tostado y chocolate con leche.'),
    dict(sku='GC-006', short='Sumatra Mandheling', country='Indonesia', origin='ID', region='Sumatra',
         varieties=['Variedades locales'], alt=None, process='Semilavado', roast='dark',
         weight=340, price='14.00', stock=3, notes='Tierra húmeda, cedro y especias.'),
    # Costa Rica: un café por región, con los nombres de región del ICAFE de 2025.
    dict(sku='GC-007', short='Dota', country='Costa Rica', origin='CR', region='Los Santos',
         varieties=['Caturra', 'Catuaí'], alt=1750, process='Lavado', roast='medium',
         weight=340, price='16.50', stock=14, notes='Chocolate, naranja y acidez brillante.'),
    dict(sku='GC-008', short='Sarchí', country='Costa Rica', origin='CR', region='Valle Occidental',
         varieties=['Villa Sarchí'], alt=1450, process='Honey amarillo', roast='light',
         weight=340, price='18.00', stock=9, notes='Panela, durazno y miel.'),
    dict(sku='GC-009', short='Tres Ríos', country='Costa Rica', origin='CR', region='Valle Central',
         varieties=['Villalobos'], alt=1500, process='Lavado', roast='medium',
         weight=340, price='17.00', stock=11, notes='Caramelo, almendra y manzana roja.'),
    dict(sku='GC-010', short='Orosi', country='Costa Rica', origin='CR', region='Turrialba',
         varieties=['Centroamericano (H1)'], alt=1200, process='Lavado', roast='medium',
         weight=340, price='14.50', stock=16, notes='Cacao, nuez y cuerpo medio.'),
    dict(sku='GC-011', short='Rivas', country='Costa Rica', origin='CR', region='Pérez Zeledón',
         varieties=['Geisha'], alt=1650, process='Natural', roast='light',
         weight=250, price='26.00', stock=2, notes='Jazmín, frutos rojos y bergamota.'),
    dict(sku='GC-012', short='San Vito', country='Costa Rica', origin='CR', region='Coto Brus',
         varieties=['Catuaí'], alt=1300, process='Honey rojo', roast='medium',
         weight=340, price='16.00', stock=7, notes='Cereza, panela y cuerpo sedoso.'),
    dict(sku='GC-013', short='Hojancha', country='Costa Rica', origin='CR', region='Zona Norte',
         varieties=['Costa Rica 95'], alt=1000, process='Lavado', roast='dark',
         weight=500, price='13.50', stock=18, notes='Chocolate amargo, especias y cuerpo pleno.'),
]

ROAST_ES = {'light': 'Claro', 'medium': 'Medio', 'dark': 'Oscuro'}


def fold(s):
    return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().lower()


def name(p):
    return f"{p['short']}, {p['country']}, {p['weight']} g"


VARIETIES = sorted({v for p in P for v in p['varieties']}, key=fold)
ORIGINS = sorted({(p['origin'], p['country']) for p in P})
CR = [p for p in P if p['origin'] == 'CR']

SOURCES = {
    'ef': 'https://www.elfinancierocr.com/economia-y-politica/tres-rios-desaparece-del-mapa-de-las-regiones/YPE3AYVL7JHVFOHPLYZM3VWHQM/story/',
    'wcr_t5296': 'https://varieties.worldcoffeeresearch.org/varieties/t5296',
    'oz_villa_sarchi': 'https://ozonecoffee.co.uk/blogs/varietals/coffee-varietal-villa-sarchi',
    'oz_caturra': 'https://ozonecoffee.co.uk/blogs/varietals/coffee-varietal-caturra',
    'oz_catuai': 'https://ozonecoffee.co.uk/blogs/varietals/coffee-varietal-catuai',
    'oz_h1': 'https://ozonecoffee.co.uk/blogs/varietals/coffee-varietal-centroamericano',
    'sm_villalobos': 'https://library.sweetmarias.com/glossary/villalobos/',
    'sm_cr95': 'https://library.sweetmarias.com/glossary/costa-rica-95-cr95-variety/',
    'wiki_geisha': 'https://en.wikipedia.org/wiki/Geisha_(coffee)',
}

# Guía: solo afirmaciones comprobadas en las fuentes (orden alfabético).
GUIDE = [
    ('Catuaí', 'Cruce de Caturra amarillo y Mundo Novo, hecho en 1949 en el Instituto Agronômico de Campinas (Brasil) y liberado en 1972.'),
    ('Caturra', 'Mutación natural enana de Bourbon, descubierta en Minas Gerais (Brasil) entre 1915 y 1918.'),
    ('Centroamericano (H1)', 'Híbrido F1 entre T5296, una línea Sarchimor, y Rume Sudan. Lo desarrollaron CIRAD, PROMECAFE y el CATIE, y se liberó en 2010.'),
    ('Costa Rica 95', 'Catimor (Híbrido de Timor × Caturra) que el ICAFE seleccionó por su rendimiento y su resistencia a la roya y al ojo de gallo; hoy es susceptible a ambas enfermedades.'),
    ('Geisha', 'Originaria del bosque de Gori Gesha, en Etiopía. En 1953 llegó al CATIE, en Costa Rica.'),
    ('Villa Sarchí', 'Mutación natural enana de Bourbon, hallada en el noroeste de Alajuela en las décadas de 1950 o 1960. Es uno de los progenitores del Sarchimor original y, por esa vía, de T5296 y de Centroamericano.'),
    ('Villalobos', 'Mutación natural enana de Typica, presente sobre todo en Costa Rica.'),
]
