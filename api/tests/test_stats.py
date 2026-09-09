import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from scipy import stats as scipy_stats

from radar_api.stats import percentil, zscore


def _percentil_forca_bruta(valores: list[float], x: float) -> float:
    menores = sum(1 for v in valores if v < x)
    iguais = sum(1 for v in valores if v == x)
    return percentil(menores, iguais, len(valores))


def test_percentil_conferido_a_mao():
    # [10, 20, 30, 40]; x=30 tem 2 menores e 1 igual -> (2 + 0.5)/4 = 62.5%
    assert percentil(n_menores=2, n_iguais=1, n_total=4) == pytest.approx(62.5)


def test_percentil_do_minimo_e_do_maximo():
    valores = [10.0, 20.0, 30.0, 40.0]
    assert _percentil_forca_bruta(valores, 10.0) == pytest.approx(12.5)
    assert _percentil_forca_bruta(valores, 40.0) == pytest.approx(87.5)


def test_empates_distribuidos_simetricamente():
    # Sem a correcao de 0.5, um bloco de empates iria todo para um dos lados.
    valores = [5.0] * 10
    assert _percentil_forca_bruta(valores, 5.0) == pytest.approx(50.0)


def test_recorte_vazio_nao_divide_por_zero():
    with pytest.raises(ValueError, match="vazio"):
        percentil(n_menores=0, n_iguais=0, n_total=0)


@pytest.mark.parametrize(
    "valores",
    [
        [10.0, 20.0, 30.0, 40.0],
        [5.0] * 10,
        [1.0, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0],
        [420.5, 512.3, 512.3, 700.0, 1000.0],
    ],
)
def test_bate_com_scipy_percentileofscore_kind_mean(valores):
    for x in {*valores, 0.0, 999.9}:
        esperado = scipy_stats.percentileofscore(valores, x, kind="mean")
        assert _percentil_forca_bruta(valores, x) == pytest.approx(esperado)


@given(
    st.lists(st.floats(0, 1000, allow_nan=False), min_size=1, max_size=60),
    st.floats(0, 1000, allow_nan=False),
)
def test_percentil_sempre_entre_0_e_100(valores, x):
    assert 0.0 <= _percentil_forca_bruta(valores, x) <= 100.0


@given(st.lists(st.floats(0, 1000, allow_nan=False), min_size=1, max_size=40))
def test_percentil_e_monotonico(valores):
    a, b = 200.0, 800.0
    assert _percentil_forca_bruta(valores, a) <= _percentil_forca_bruta(valores, b)


def test_zscore_da_media_e_zero():
    assert zscore(500.0, media=500.0, desvio=100.0) == pytest.approx(0.0)


def test_zscore_bate_com_numpy():
    valores = np.array([420.5, 512.3, 700.0, 1000.0])
    media, desvio = valores.mean(), valores.std(ddof=1)
    assert zscore(700.0, media, desvio) == pytest.approx((700.0 - media) / desvio)


def test_zscore_com_desvio_zero_e_indefinido():
    # Recorte onde todo mundo tirou a mesma nota: distancia em desvios nao existe.
    assert zscore(500.0, media=500.0, desvio=0.0) is None
