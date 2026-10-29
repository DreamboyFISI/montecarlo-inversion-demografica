package main

import (
	"math"
	"math/rand/v2"

	"gonum.org/v1/gonum/stat/distuv"
)

type Step struct {
	Population     Population
	Births, Deaths int64
	Lambda         float64
}

func total(p Population) int64 {
	var n int64
	for s := 0; s < 2; s++ {
		for _, v := range p[s] {
			n += v
		}
	}
	return n
}
func between(p Population, from, to int) int64 {
	var n int64
	for s := 0; s < 2; s++ {
		for a := from; a <= to; a++ {
			n += p[s][a]
		}
	}
	return n
}
func inverted(p Population) bool { return between(p, 65, 100) > between(p, 0, 14) }
func splitmix64(x uint64) uint64 {
	x += 0x9e3779b97f4a7c15
	x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9
	x = (x ^ (x >> 27)) * 0x94d049bb133111eb
	return x ^ (x >> 31)
}

// poisson usa inversion para medias pequenas y PTRS (Hormann) para medias grandes.
func poisson(lambda float64, r *rand.Rand) int64 {
	if lambda <= 0 {
		return 0
	}
	if lambda < 10 {
		limit, product, k := math.Exp(-lambda), 1.0, int64(0)
		for product > limit {
			k++
			product *= r.Float64()
		}
		return k - 1
	}
	sqrt := math.Sqrt(lambda)
	b := .931 + 2.53*sqrt
	a := -.059 + .02483*b
	invAlpha := 1.1239 + 1.1328/(b-3.4)
	vr := .9277 - 3.6224/(b-2)
	for {
		u := r.Float64() - .5
		v := r.Float64()
		us := .5 - math.Abs(u)
		k := int64(math.Floor((2*a/us+b)*u + lambda + .43))
		if us >= .07 && v <= vr && k >= 0 {
			return k
		}
		if k < 0 || (us < .013 && v > us) {
			continue
		}
		lhs := math.Log(v * invAlpha / (a/(us*us) + b))
		lg, _ := math.Lgamma(float64(k) + 1)
		if lhs <= -lambda+float64(k)*math.Log(lambda)-lg {
			return k
		}
	}
}

// Sorteo binomial exacto mediante el algoritmo de rechazo de Gonum.
func binomial(n int64, p float64, r *rand.Rand) int64 {
	if n <= 0 || p <= 0 {
		return 0
	}
	if p >= 1 {
		return n
	}
	return int64(distuv.Binomial{N: float64(n), P: p, Src: r}.Rand())
}

func simulateYear(p Population, q Rates, f Fertility, c Config, r *rand.Rand) Step {
	step := Step{}
	for age := 15; age <= 49; age++ {
		step.Lambda += float64(p[Women][age]) * f[age]
	}
	step.Births = poisson(step.Lambda, r)
	female := binomial(step.Births, c.FemaleProbability, r)
	born := [2]int64{step.Births - female, female}
	for sex := 0; sex < 2; sex++ {
		for age := 0; age <= 100; age++ {
			deaths := binomial(p[sex][age], q[sex][age], r)
			step.Deaths += deaths
			next := age + 1
			if next > 100 {
				next = 100
			}
			step.Population[sex][next] += p[sex][age] - deaths
		}
		alive := binomial(born[sex], c.NewbornSurvival[sex], r)
		step.Population[sex][0] = alive
		step.Deaths += born[sex] - alive
	}
	return step
}
