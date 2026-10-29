package main

import (
	"encoding/csv"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

const Ages = 101
const Men, Women = 0, 1

type Population [2][Ages]int64
type Rates [2][Ages]float64
type Fertility [Ages]float64

func readCSV(path string) ([][]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.TrimLeadingSpace = true
	rows, err := r.ReadAll()
	if err != nil {
		return nil, err
	}
	for i := range rows {
		for j := range rows[i] {
			rows[i][j] = strings.TrimSpace(rows[i][j])
		}
	}
	return rows, nil
}

func loadPopulation(dir string) (Population, error) {
	rows, err := readCSV(filepath.Join(dir, "poblacion_inicial_peru.csv"))
	if err != nil {
		return Population{}, err
	}
	if len(rows) != 22 {
		return Population{}, fmt.Errorf("se requieren 21 grupos de poblacion")
	}
	var p Population
	for _, row := range rows[1:] {
		start := 100
		if row[0] != "100+" {
			start, err = strconv.Atoi(strings.Split(row[0], "-")[0])
			if err != nil {
				return p, err
			}
		}
		for sex := 0; sex < 2; sex++ {
			count, e := strconv.ParseInt(row[sex+1], 10, 64)
			if e != nil || count < 0 {
				return p, fmt.Errorf("poblacion invalida")
			}
			if start == 100 {
				p[sex][100] = count
			} else {
				for j := 0; j < 5; j++ {
					p[sex][start+j] = count / 5
					if int64(j) < count%5 {
						p[sex][start+j]++
					}
				}
			}
		}
	}
	return p, nil
}

func loadMortality(dir string, c Config) (Rates, error) {
	rows, err := readCSV(filepath.Join(dir, "mortalidad_peru.csv"))
	if err != nil {
		return Rates{}, err
	}
	if len(rows) != 23 {
		return Rates{}, fmt.Errorf("se requieren 22 filas de mortalidad")
	}
	var q Rates
	for _, row := range rows[1:] {
		key, e := strconv.Atoi(row[0])
		if e != nil {
			return q, e
		}
		for sex := 0; sex < 2; sex++ {
			value, e := strconv.ParseFloat(row[sex+1], 64)
			if e != nil || value < 0 || value > 1 {
				return q, fmt.Errorf("mortalidad invalida")
			}
			if key == 100 {
				q[sex][100] = c.Q100[sex]
				continue
			}
			n := 5
			if key == 0 {
				n = 1
			} else if key == 1 {
				n = 4
			}
			annual := value
			if c.MortalityType == "supervivencia_anual" {
				annual = 1 - value
			} else if c.MortalityType == "supervivencia_intervalo" {
				annual = 1 - math.Pow(value, 1/float64(n))
			}
			for age := key; age < key+n; age++ {
				q[sex][age] = math.Max(0, math.Min(1, annual))
			}
		}
	}
	return q, nil
}

func loadFertility(dir string, c Config) ([]Fertility, error) {
	rows, err := readCSV(filepath.Join(dir, "fecundidad_peru.csv"))
	if err != nil {
		return nil, err
	}
	if len(rows) != 8 || len(rows[0]) != 11 {
		return nil, fmt.Errorf("estructura de fecundidad invalida")
	}
	type period struct{ from, to, col int }
	periods := []period{}
	for col, header := range rows[0][1:] {
		parts := strings.Split(strings.TrimPrefix(header, "poblacion_"), "_")
		if len(parts) != 2 {
			return nil, fmt.Errorf("periodo invalido")
		}
		from, e1 := strconv.Atoi(parts[0])
		to, e2 := strconv.Atoi(parts[1])
		if e1 != nil || e2 != nil {
			return nil, fmt.Errorf("periodo invalido")
		}
		periods = append(periods, period{from, to, col + 1})
	}
	result := make([]Fertility, c.Horizon)
	for t := 0; t < c.Horizon; t++ {
		year, col := c.BaseYear+t, -1
		for _, p := range periods {
			if year >= p.from && year < p.to {
				col = p.col
			}
		}
		if col < 0 {
			return nil, fmt.Errorf("fecundidad sin cobertura para %d", year)
		}
		for _, row := range rows[1:] {
			age, _ := strconv.Atoi(strings.Split(row[0], "-")[0])
			value, e := strconv.ParseFloat(row[col], 64)
			if e != nil || value < 0 || value > 1 {
				return nil, fmt.Errorf("fecundidad invalida")
			}
			for j := 0; j < 5; j++ {
				result[t][age+j] = value
			}
		}
	}
	return result, nil
}
