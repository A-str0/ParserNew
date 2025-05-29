a = ["a", "b", "c"]
print([(lambda x: x == "a")(b) for b in a])