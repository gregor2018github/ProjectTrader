class Player:
    def __init__(self, name, cost_of_living):
        self.name = name
        self.score = 0
        self.reputation = 0
        self.daily_cost_of_living = cost_of_living
        self.position = (0, 0)  # Default position, can be updated later

    def add_score(self, score):
        self.score += score
    
    def change_reputation(self, reputation):
        self.reputation += reputation

    def change_daily_cost_of_living(self, cost):
        self.daily_cost_of_living += cost

    def __str__(self):
        return f"{self.name} has {self.score} points"