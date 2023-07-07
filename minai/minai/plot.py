import matplotlib.pyplot as plt
plt.style.use("dark_background")
def p():
    plt.plot(range(10), [x**2 for x in range(10)])
