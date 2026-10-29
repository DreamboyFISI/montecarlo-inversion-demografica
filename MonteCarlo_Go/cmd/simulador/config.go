package main

import (
	"bufio"
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Config struct {
	BaseYear, Horizon int
	Scenarios         int64
	Seed              uint64
	DataStatus        string
	MortalityType     string
	FemaleProbability float64
	NewbornSurvival   [2]float64
	Q100              [2]float64
	FertilitySigma    float64
	MortalitySigma    float64
}

func loadConfig(path string) (Config, error) {
	f, err := os.Open(path)
	if err != nil {
		return Config{}, fmt.Errorf("no se puede leer configuracion: %w", err)
	}
	defer f.Close()
	values := map[string]string{}
	s := bufio.NewScanner(f)
	for s.Scan() {
		line := strings.TrimSpace(s.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			return Config{}, fmt.Errorf("se espera clave=valor")
		}
		key, value := strings.TrimSpace(parts[0]), strings.TrimSpace(parts[1])
		if _, exists := values[key]; exists {
			return Config{}, fmt.Errorf("clave duplicada: %s", key)
		}
		values[key] = value
	}
	if err := s.Err(); err != nil {
		return Config{}, err
	}
	required := []string{"anio_base", "horizonte", "escenarios", "semilla", "estado_datos", "tipo_mortalidad",
		"unidad_fecundidad", "p_femenino", "u_recien_nacido_h", "u_recien_nacido_f", "q_100_h", "q_100_f"}
	for _, key := range required {
		if values[key] == "" {
			return Config{}, fmt.Errorf("falta parametro: %s", key)
		}
	}
	atoi := func(key string) (int64, error) { return strconv.ParseInt(values[key], 10, 64) }
	atof := func(key string, optional bool) (float64, error) {
		if optional && values[key] == "" {
			return 0, nil
		}
		v, err := strconv.ParseFloat(values[key], 64)
		if err != nil || v < 0 || v > 1 {
			return 0, fmt.Errorf("valor invalido para %s", key)
		}
		return v, nil
	}
	year, err := atoi("anio_base")
	if err != nil {
		return Config{}, err
	}
	horizon, err := atoi("horizonte")
	if err != nil {
		return Config{}, err
	}
	scenarios, err := atoi("escenarios")
	if err != nil {
		return Config{}, err
	}
	seed, err := strconv.ParseUint(values["semilla"], 10, 64)
	if err != nil {
		return Config{}, err
	}
	pf, err := atof("p_femenino", false)
	if err != nil {
		return Config{}, err
	}
	uh, err := atof("u_recien_nacido_h", false)
	if err != nil {
		return Config{}, err
	}
	uf, err := atof("u_recien_nacido_f", false)
	if err != nil {
		return Config{}, err
	}
	qh, err := atof("q_100_h", false)
	if err != nil {
		return Config{}, err
	}
	qf, err := atof("q_100_f", false)
	if err != nil {
		return Config{}, err
	}
	sf, err := atof("sigma_fecundidad", true)
	if err != nil || sf > .5 {
		return Config{}, fmt.Errorf("sigma_fecundidad invalida")
	}
	sm, err := atof("sigma_mortalidad", true)
	if err != nil || sm > .5 {
		return Config{}, fmt.Errorf("sigma_mortalidad invalida")
	}
	if year < 1900 || year > 2100 || horizon < 1 || horizon > 150 || scenarios < 1 || scenarios > 1_000_000_000 {
		return Config{}, fmt.Errorf("configuracion fuera de limites")
	}
	if values["unidad_fecundidad"] != "anual_por_mujer" {
		return Config{}, fmt.Errorf("unidad de fecundidad no soportada")
	}
	return Config{int(year), int(horizon), scenarios, seed, values["estado_datos"], values["tipo_mortalidad"],
		pf, [2]float64{uh, uf}, [2]float64{qh, qf}, sf, sm}, nil
}
