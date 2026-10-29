package main

import (
	"encoding/csv"
	"flag"
	"fmt"
	"math"
	"math/rand/v2"
	"os"
	"path/filepath"
	"strconv"
	"time"
)

type Metrics struct {
	Scenarios                             int64
	Horizon                               int
	Load, Simulation, Total, CPU, PeakMiB float64
}

func must(err error) {
	if err != nil {
		panic(err)
	}
}
func writeRow(w *csv.Writer, values ...any) {
	row := make([]string, len(values))
	for i, v := range values {
		row[i] = fmt.Sprint(v)
	}
	must(w.Write(row))
}

func main() {
	configPath := flag.String("config", "", "archivo de configuracion")
	dataDir := flag.String("datos", "datos", "carpeta de datos")
	outputDir := flag.String("salida", "resultados", "carpeta de salida")
	scenariosOverride := flag.Int64("escenarios", 0, "numero de escenarios")
	flag.Parse()
	if *configPath == "" {
		fmt.Fprintln(os.Stderr, "Error: indique --config")
		os.Exit(1)
	}
	if err := run(*configPath, *dataDir, *outputDir, *scenariosOverride); err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		os.Exit(1)
	}
}

func run(configPath, dataDir, outputDir string, override int64) error {
	started := time.Now()
	c, err := loadConfig(configPath)
	if err != nil {
		return err
	}
	if override > 0 {
		c.Scenarios = override
	}
	dataStart := time.Now()
	initial, err := loadPopulation(dataDir)
	if err != nil {
		return err
	}
	baseQ, err := loadMortality(dataDir, c)
	if err != nil {
		return err
	}
	baseF, err := loadFertility(dataDir, c)
	if err != nil {
		return err
	}
	metrics := Metrics{Scenarios: c.Scenarios, Horizon: c.Horizon, Load: time.Since(dataStart).Seconds()}
	if _, err := os.Stat(outputDir); err == nil {
		return fmt.Errorf("la carpeta de salida ya existe")
	}
	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return err
	}
	configBytes, err := os.ReadFile(configPath)
	if err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(outputDir, "config_usada.ini"), configBytes, 0644); err != nil {
		return err
	}
	params := fmt.Sprintf("estado_datos=%s\nanio_base=%d\nhorizonte=%d\nescenarios=%d\nsemilla=%d\ntipo_mortalidad=%s\n"+
		"sigma_fecundidad=%g\nsigma_mortalidad=%g\nVersion Go secuencial; sorteos Poisson y binomial exactos.\n",
		c.DataStatus, c.BaseYear, c.Horizon, c.Scenarios, c.Seed, c.MortalityType, c.FertilitySigma, c.MortalitySigma)
	if err := os.WriteFile(filepath.Join(outputDir, "parametros_efectivos.txt"), []byte(params), 0644); err != nil {
		return err
	}

	scenariosFile, err := os.Create(filepath.Join(outputDir, "escenarios.csv"))
	if err != nil {
		return err
	}
	defer scenariosFile.Close()
	scenariosCSV := csv.NewWriter(scenariosFile)
	defer scenariosCSV.Flush()
	writeRow(scenariosCSV, "escenario", "ocurrio_inversion", "primer_anio_inversion")
	trajectoryFile, err := os.Create(filepath.Join(outputDir, "trayectoria_escenario_1.csv"))
	if err != nil {
		return err
	}
	defer trajectoryFile.Close()
	trajectoryCSV := csv.NewWriter(trajectoryFile)
	defer trajectoryCSV.Flush()
	writeRow(trajectoryCSV, "anio", "poblacion_inicial", "nacimientos", "defunciones", "poblacion_final", "menores15", "mayores65", "lambda", "balance")
	macro := c.FertilitySigma > 0 || c.MortalitySigma > 0
	var factorsFile *os.File
	var factorsCSV *csv.Writer
	if macro {
		factorsFile, err = os.Create(filepath.Join(outputDir, "factores_escenarios.csv"))
		if err != nil {
			return err
		}
		defer factorsFile.Close()
		factorsCSV = csv.NewWriter(factorsFile)
		defer factorsCSV.Flush()
		writeRow(factorsCSV, "escenario", "factor_fecundidad", "factor_mortalidad")
	}

	histogram := make([]int64, c.Horizon+1)
	var withInversion int64
	simStart := time.Now()
	for scenario := int64(0); scenario < c.Scenarios; scenario++ {
		population := initial
		seed1 := splitmix64(c.Seed + uint64(scenario))
		seed2 := splitmix64(seed1)
		rng := rand.New(rand.NewPCG(seed1, seed2))
		first := -1
		if inverted(population) {
			first = 0
		}
		q := baseQ
		fertility := baseF
		if macro {
			ff, fm := 1.0, 1.0
			if c.FertilitySigma > 0 {
				ff = math.Max(0, 1+c.FertilitySigma*rng.NormFloat64())
			}
			if c.MortalitySigma > 0 {
				fm = math.Max(0, 1+c.MortalitySigma*rng.NormFloat64())
			}
			fertility = append([]Fertility(nil), baseF...)
			for i := range fertility {
				for age := range fertility[i] {
					fertility[i][age] *= ff
				}
			}
			for sex := 0; sex < 2; sex++ {
				for age := 0; age < Ages; age++ {
					q[sex][age] = math.Max(0, math.Min(1, q[sex][age]*fm))
				}
			}
			writeRow(factorsCSV, scenario+1, strconv.FormatFloat(ff, 'g', 10, 64), strconv.FormatFloat(fm, 'g', 10, 64))
		}
		for year := 0; year < c.Horizon; year++ {
			before := total(population)
			step := simulateYear(population, q, fertility[year], c, rng)
			population = step.Population
			if first < 0 && inverted(population) {
				first = year + 1
			}
			if scenario == 0 {
				writeRow(trajectoryCSV, c.BaseYear+year+1, before, step.Births, step.Deaths, total(population), between(population, 0, 14), between(population, 65, 100), strconv.FormatFloat(step.Lambda, 'g', 15, 64), total(population)-before-step.Births+step.Deaths)
			}
		}
		if first >= 0 {
			withInversion++
			histogram[first]++
			writeRow(scenariosCSV, scenario+1, 1, c.BaseYear+first)
		} else {
			writeRow(scenariosCSV, scenario+1, 0, "")
		}
	}
	scenariosCSV.Flush()
	trajectoryCSV.Flush()
	if factorsCSV != nil {
		factorsCSV.Flush()
	}
	metrics.Simulation = time.Since(simStart).Seconds()
	metrics.Total = time.Since(started).Seconds()
	metrics.CPU = metrics.Total
	metrics.PeakMiB = peakMemoryMiB()
	if err := writeDistribution(outputDir, c, histogram); err != nil {
		return err
	}
	if err := writeMetrics(outputDir, metrics); err != nil {
		return err
	}
	if err := writeSummary(outputDir, c, initial, histogram, withInversion, metrics); err != nil {
		return err
	}
	fmt.Printf("Completado: %d escenarios con Go. Resultados en: %s\nTiempo total: %.6f s\n", c.Scenarios, outputDir, metrics.Total)
	return nil
}

func writeDistribution(dir string, c Config, histogram []int64) error {
	f, err := os.Create(filepath.Join(dir, "distribucion.csv"))
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()
	writeRow(w, "anio", "primeras_inversiones", "probabilidad_anual", "probabilidad_acumulada")
	var accumulated int64
	for step, count := range histogram {
		accumulated += count
		writeRow(w, c.BaseYear+step, count,
			strconv.FormatFloat(float64(count)/float64(c.Scenarios), 'g', 15, 64), strconv.FormatFloat(float64(accumulated)/float64(c.Scenarios), 'g', 15, 64))
	}
	return nil
}

func writeMetrics(dir string, m Metrics) error {
	f, err := os.Create(filepath.Join(dir, "metricas.csv"))
	if err != nil {
		return err
	}
	defer f.Close()
	w := csv.NewWriter(f)
	defer w.Flush()
	writeRow(w, "version", "procesos", "hilos", "escenarios", "horizonte", "segundos_carga", "segundos_simulacion", "segundos_total", "segundos_cpu", "ms_por_escenario", "escenarios_por_segundo", "escenario_anios_por_segundo", "memoria_pico_mib")
	throughput := float64(m.Scenarios) / m.Simulation
	writeRow(w, "go_secuencial", 1, 1, m.Scenarios, m.Horizon, m.Load, m.Simulation, m.Total, m.CPU,
		m.Simulation*1000/float64(m.Scenarios), throughput, throughput*float64(m.Horizon), m.PeakMiB)
	return nil
}

func writeSummary(dir string, c Config, initial Population, histogram []int64, with int64, m Metrics) error {
	var sum int64
	minYear, maxYear := 0, 0
	for step, count := range histogram {
		if count > 0 {
			year := c.BaseYear + step
			if minYear == 0 {
				minYear = year
			}
			maxYear = year
			sum += int64(year) * count
		}
	}
	text := fmt.Sprintf("ESTADO: %s\nVersion: Go secuencial, un proceso, un hilo.\nPoblacion inicial: %d\nMenores de 15: %d\n65 o mas: %d\nEscenarios completados: %d\nHorizonte: %d\nCon inversion: %d\nSin inversion: %d\nProbabilidad de inversion: %.12g\nSegundos simulacion: %.9f\nSegundos total: %.9f\nMemoria pico (MiB): %.6f\n",
		c.DataStatus, total(initial), between(initial, 0, 14), between(initial, 65, 100), c.Scenarios, c.Horizon, with, c.Scenarios-with, float64(with)/float64(c.Scenarios), m.Simulation, m.Total, m.PeakMiB)
	if with > 0 {
		text += fmt.Sprintf("Primer anio de inversion: minimo %d, media %.6f, maximo %d\n", minYear, float64(sum)/float64(with), maxYear)
	}
	return os.WriteFile(filepath.Join(dir, "resumen.txt"), []byte(text), 0644)
}
