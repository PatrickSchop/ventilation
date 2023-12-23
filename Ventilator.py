class DemandCalculator:
    __calculatedDemand = 0
    __externalDemand = 0
    __currentDemand = -1

    __demandChanged = None

    @property
    def demandChanged(self):
        return self.__demandChanged
    
    @demandChanged.setter
    def demandChanged(self, dc):
        self.__demandChanged = dc


    def demand(self, demand):
        self.__externalDemand = demand
        self.__updateDemand()


    def __updateDemand(self):
        print(f"updating demand {self.__calculatedDemand} {self.__externalDemand}")
        demand = max(self.__calculatedDemand, self.__externalDemand)
        if (demand != self.__currentDemand):
            self.__currentDemand = demand

            if not (self.__demandChanged == None):
                print(f"demandChanged callback with {self.__currentDemand}")
                self.demandChanged(self.__currentDemand)