library(dplyr)
library(ggplot2)
data = read.csv("C:\\Users\\jtmurphy\\Projects\\CRCI\\fema_cria\\data\\basic_scores.csv")
#data <- filter(data, Indicator!="RACE")

data <- na.omit(data)

data$region[data$state_abbr=="PR"] = "PR"
#data$region[data$state_abbr=="AK"] = "AK"

data$region[data$region == "Region I"] = "New England"
#data$region[data$region == "Region II"] = "NY/NJ/PR"
data$region[data$region == "Region II"] = "NY/NJ"
data$region[data$region == "Region III"] = "Middle Atlantic"
data$region[data$region == "Region IV"] = "Southeast"
data$region[data$region == "Region V"] = "Midwest"
data$region[data$region == "Region VI"] = "Southwest"
data$region[data$region == "Region VII"] = "Plains"
data$region[data$region == "Region VIII"] = "Mountain West"
data$region[data$region == "Region IX"] = "Southwest Coast"
data$region[data$region == "Region X"] = "Pacific Northwest"

# Add the regional population
regionalPopStep1 = na.omit(filter(data, Indicator=="Education"))
regionalPopStep1$Indicator = NULL
regionalPop = regionalPopStep1 %>% group_by(region) %>% summarize(region_pop = sum(B02001_001E))
rm(regionalPopStep1)

data <- merge(data, regionalPop, by="region")


# Scale all scores from 0 to 1 based on max and min in the data set
# Do this nationally and within region
data <- data %>% group_by(Indicator) %>% mutate(scaled_score = (value - min(value)) / (max(value) - min(value)))
data <- data %>% group_by(region, Indicator) %>% mutate(scaled_score_region = (value - min(value)) / (max(value) - min(value)))


# Get national avg, z score
data <- data %>% group_by(Indicator) %>% mutate(natlz = (value - mean(value))/ sd(value))

# Get regional z score
data <- data %>% group_by(region, Indicator) %>% mutate(rgnlz = (value - mean(value))/ sd(value))


# Scale county ranks based on value
# National Rank
data <- data %>% arrange(Indicator, value) %>% group_by(Indicator) %>% mutate(national_rank = row_number(value))

# Regional Rank
data <- data %>% arrange(region, Indicator, value) %>% group_by(region, Indicator) %>% mutate(rank = row_number(value))

# Scale within region and indicator
data <- data %>% group_by(region, Indicator) %>% mutate(scaled_rank = (rank / max(rank)))

# Scale with cumulative sum
data <- data %>% group_by(region, Indicator) %>% mutate(scaled_rank_by_pop = cumsum(B02001_001E))
data$scaled_xpos = data$scaled_rank_by_pop / data$region_pop 

# Do any filtering...
dataToPlot <- data
#dataToPlot <- filter(data, Indicator!="Inactive Voter" | scaled_score != 0)
#dataToPlot <- filter(data, region=="PR" | region=="Region II")
#dataToPlot <- filter(data, region=="AK" | region=="Region X")

#dataToPlot <- filter(dataToPlot, Indicator=="Median Income")
#dataToPlot <- filter(dataToPlot, region=="Midwest" | region=="NY/NJ")


test <- filter(data, Indicator=="Inactive Voter" & state_abbr=="IA")

# Various plots
# Plot 1
# X = county rank (national)
# y = scaled value (national)
# facet = Indicator
# Color = region
plot = ggplot(data=dataToPlot, aes(x=national_rank, y=scaled_score, color=region)) + geom_point() + facet_wrap(~ Indicator) + ggtitle("Indicators (scaled by national range) increasing by county, national")
print(plot)
ggsave("C:\\Users\\jtmurphy\\Projects\\CRCI\\plot_1.pdf", width=17, height=8.5, units="in")

# Plot 2
# x = county rank (regional)
# y = scale value (national)
# facet = Indicator
# color = region
plot = ggplot(data=dataToPlot, aes(x=rank, y=scaled_score, color=region)) + geom_point() + facet_wrap(~ Indicator) + ggtitle("Indicators (scaled by national range) increasing by county, regional")
print(plot)
ggsave("C:\\Users\\jtmurphy\\Projects\\CRCI\\plot_2.pdf", width=17, height=8.5, units="in")

# Plot 3
# x = county rank (regional, scaled)
# y = scale value (national)
# facet = Indicator
# color = region
plot = ggplot(data=dataToPlot, aes(x=scaled_rank, y=scaled_score, color=region)) + geom_point() + facet_wrap(~ Indicator) + ggtitle("Indicators (scaled by national range) increasing by county, scaled regional")
print(plot)
ggsave("C:\\Users\\jtmurphy\\Projects\\CRCI\\plot_3.pdf", width=17, height=8.5, units="in")

# Plot 4
# x = county rank (regional, scaled by population)
# y = scale value (national)
# facet = Indicator
# color = region
plot = ggplot(data=dataToPlot, aes(x=scaled_xpos, y=scaled_score, color=region)) + geom_point() + geom_line() + facet_wrap(~ Indicator) + ggtitle("Indicators (scaled by national range) increasing by county, scaled by regional population")
print(plot)
ggsave("C:\\Users\\jtmurphy\\Projects\\CRCI\\plot_6.pdf", width=17, height=8.5, units="in")
# Also used for 'Plot 6', with PR broken out separately

# Plot 5
# x = county rank (regional, scaled by population)
# y = scale value (regional)
# facet = Indicator
# color = region
plot = ggplot(data=dataToPlot, aes(x=scaled_xpos, y=scaled_score_region, color=region)) + geom_point() + geom_line() + facet_wrap(~ Indicator) + ggtitle("Indicators (scaled by regional range) increasing by county, scaled by regional population")
print(plot)
ggsave("C:\\Users\\jtmurphy\\Projects\\CRCI\\plot_5.pdf", width=17, height=8.5, units="in")



# Plot 6 (use plot 4)

# Plot 7
# x = county rank (regional, scaled by population)
# y = scale value (national)
# facet = Indicator
# color = region
plot = ggplot(data=dataToPlot, aes(x=scaled_xpos, y=scaled_score, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (scaled by national range) increasing by county, scaled by regional population")
print(plot)
ggsave("C:\\Users\\jtmurphy\\Projects\\CRCI\\plot_7.pdf", width=17, height=8.5, units="in")





# Plots of all indicators by region
# Basic plot: All indicators raw values, by rank order of counties
plot = ggplot(data=dataToPlot, aes(x=rank, y=value, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (raw) increasing by county")
print(plot)

plot = ggplot(data=dataToPlot, aes(x=rank, y=rgnlz, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (raw) increasing by county")
print(plot)






# Plots of all regions by indicator

# Values:
# value
# scaled_score
# scaled_score_region
# natlz
# regnlz

# Xpositions:
# rank
# scaled_rank
# scaled_rank_by_pop

# Value
plot = ggplot(data=dataToPlot, aes(x=rank, y=value, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (raw) increasing by county")
print(plot)

plot = ggplot(data=dataToPlot, aes(x=scaled_rank, y=value, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (raw) increasing (scaled by county)")
print(plot)

plot = ggplot(data=dataToPlot, aes(x=scaled_xpos, y=value, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (raw) increasing (scaled by county population")
print(plot)

# Scaled Score
plot = ggplot(data=dataToPlot, aes(x=rank, y=scaled_score, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (scaled 0-1) increasing by county")
print(plot)

plot = ggplot(data=dataToPlot, aes(x=scaled_rank, y=scaled_score, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (scaled 0-1) increasing (scaled by county)")
print(plot)

plot = ggplot(data=dataToPlot, aes(x=scaled_xpos, y=scaled_score, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (scaled 0-1) increasing (scaled by county population")
print(plot)


# Scaled Score by region
plot = ggplot(data=dataToPlot, aes(x=rank, y=scaled_score_region, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (scaled 0-1 by region) increasing by county")
print(plot)

plot = ggplot(data=dataToPlot, aes(x=scaled_rank, y=scaled_score_region, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (scaled 0-1 by region) increasing (scaled by county)")
print(plot)

plot = ggplot(data=dataToPlot, aes(x=scaled_xpos, y=scaled_score_region, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (scaled 0-1 by region) increasing (scaled by county population)")
print(plot)

# National z
plot = ggplot(data=dataToPlot, aes(x=rank, y=natlz, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (Z) increasing by county")
print(plot)

plot = ggplot(data=dataToPlot, aes(x=scaled_rank, y=natlz, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (z) increasing (scaled by county)")
print(plot)

plot = ggplot(data=dataToPlot, aes(x=scaled_xpos, y=natlz, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (z) increasing (scaled by county population")
print(plot)


# Regional z
plot = ggplot(data=dataToPlot, aes(x=rank, y=rgnlz, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (z by region) increasing by county")
print(plot)

plot = ggplot(data=dataToPlot, aes(x=scaled_rank, y=rgnlz, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (z by region) increasing (scaled by county)")
print(plot)

plot = ggplot(data=dataToPlot, aes(x=scaled_xpos, y=rgnlz, color=Indicator)) + geom_point() + geom_line() + facet_wrap(~ region) + ggtitle("Indicators (z by region) increasing (scaled by county population")
print(plot)




plot = ggplot(data=dataToPlot, aes(x=scaled_xpos, y=scaled_score, color=region)) + geom_point() + geom_line() + facet_wrap(~ Indicator)
print(plot)

rm(plot)
#plot3 = ggplot(data=dataToPlot, aes(x=xpos, y=value, color=region)) + geom_point() + geom_line() + facet_wrap(~ Indicator)
#print(plot3)


#inspect <-filter(dataToPlot, region=="Region X" & Indicator=="Inactive Voter")



RaceOnly <- filter(dataToPlot, Indicator=="RACE")
NoRace <- filter(dataToPlot, Indicator != "RACE")
MERGED <-merge(RaceOnly,NoRace, by.x="GEO_ID", by.y="GEO_ID")
plot = ggplot(data=MERGED, aes(x=value.x, y=scaled_score.y,color=region.x)) + geom_point() + 
  geom_smooth(method="lm") + facet_wrap(~ Indicator.y) + labs(x="% non-white", y="value")
print(plot)
ggsave("C:\\Users\\jtmurphy\\Projects\\CRCI\\plot_B.pdf", width=17, height=8.5, units="in")


RaceOnly <- filter(dataToPlot, Indicator=="RACE")
NoRace <- filter(dataToPlot, Indicator != "RACE")
MERGED <-merge(RaceOnly,NoRace, by.x="GEO_ID", by.y="GEO_ID")
plot = ggplot(data=MERGED, aes(x=value.x, y=scaled_score.y)) + geom_point() + 
  geom_smooth(method="lm") + facet_wrap(~ Indicator.y) + labs(x="<- Vulnerability | Resilience->", y="percentage white")
print(plot)
ggsave("C:\\Users\\jtmurphy\\Projects\\CRCI\\plot_B_1.pdf", width=17, height=8.5, units="in")

plot = ggplot(data=MERGED, aes(x=value.x, y=scaled_score.y,color=region.x)) + geom_point(alpha=0.0) + geom_smooth(method="lm") + facet_wrap(~ Indicator.y)
print(plot)
ggsave("C:\\Users\\jtmurphy\\Projects\\CRCI\\plot_C.pdf", width=17, height=8.5, units="in")

