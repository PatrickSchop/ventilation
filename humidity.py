import math

def absoluteHumidity(relativeHumidity, temperature):
    rh = relativeHumidity
    t = temperature
    ah = (6.1112*math.exp((17.6*t)/(t+243.5))*rh*2.1674)/(273.15+t)
    return ah

print("      30    35    40    45     50     55     60     65")
for t in range(15, 31):
    ah = []
    for rh in range(30, 66, 5):
        ah.append(absoluteHumidity(t, rh))
    
    print(f"{t}    {ah[0]:.2f}  {ah[1]:.2f}  {ah[2]:.2f}  {ah[3]:.2f}  {ah[4]:.2f}  {ah[5]:.2f}  {ah[6]:.2f}  {ah[7]:.2f}")

